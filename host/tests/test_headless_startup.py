"""Headless daemon parity (spec: headless-daemon)."""

import asyncio
import json
import subprocess
import sys

import pytest

import clawd_tank_daemon.daemon as daemon_mod
import clawd_tank_menubar.hooks as hooks
import clawd_tank_menubar.preferences as preferences
from clawd_tank_daemon.daemon import _build_daemon
from clawd_tank_daemon.sim_client import SIM_DEFAULT_PORT


def prefs_file(content):
    path = preferences.PREFS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content)
    elif content is not None:
        path.write_text(json.dumps(content))
    return path


def build(*argv):
    return _build_daemon(list(argv))


def sim_of(d):
    return d._transports.get("sim")


# --- preferences -------------------------------------------------------------

@pytest.mark.parametrize("content", [None, "{not json", "[1]"])
def test_missing_or_invalid_prefs_use_defaults_and_stay_untouched(content):
    path = prefs_file(content)
    before = path.read_bytes() if path.exists() else None
    d = build()
    assert "ble" in d._transports and sim_of(d).desktop_pet is False
    assert (path.read_bytes() if path.exists() else None) == before


def test_ble_disabled_creates_no_ble_transport():
    prefs_file({"ble_enabled": False})
    assert "ble" not in build()._transports


def test_sim_enabled_default_uses_default_port():
    prefs_file({"sim_enabled": True})
    assert sim_of(build())._port == SIM_DEFAULT_PORT


def test_sim_disabled_in_prefs_creates_no_sim():
    prefs_file({"sim_enabled": False})
    assert sim_of(build()) is None


def test_flag_beats_sim_enabled_false():
    prefs_file({"sim_enabled": False})
    assert sim_of(build("--sim")) is not None


def test_desk_mode_makes_sim_a_desktop_pet():
    prefs_file({"sim_desk_mode": True})
    assert sim_of(build()).desktop_pet is True


def test_sim_window_prefs_are_ignored_headless():
    prefs_file({"sim_window_visible": False, "sim_always_on_top": False})
    assert sim_of(build()) is not None


def test_sim_only_with_port_is_unchanged_even_with_prefs():
    prefs_file({"ble_enabled": True, "sim_enabled": False})
    d = build("--sim-only", "--sim-port", "12345")
    assert "ble" not in d._transports and sim_of(d)._port == 12345


def test_flags_ignore_ble_enabled_pref():
    prefs_file({"ble_enabled": False})
    assert "ble" in build("--sim")._transports


def test_non_object_prefs_do_not_crash_loader():
    path = prefs_file("[1]")
    assert preferences.load_preferences(path) == preferences.DEFAULTS


# --- hook install on start ---------------------------------------------------

def test_no_install_hooks_skips_startup():
    assert build("--no-install-hooks")._startup is None


def test_default_startup_is_ensure_hooks_current():
    assert build()._startup is hooks.ensure_hooks_current


def test_startup_runs_only_after_lock_and_before_socket(monkeypatch):
    calls = []
    d = build()
    d._headless = False
    d._startup = lambda: calls.append("startup")
    monkeypatch.setattr(daemon_mod, "_acquire_lock", lambda takeover=False: calls.append("lock") or 3)

    async def stop(*a, **k):
        calls.append("socket")
        raise RuntimeError("stop here")

    monkeypatch.setattr(d._socket, "start", stop)
    with pytest.raises(RuntimeError):
        asyncio.run(d.run())
    assert calls == ["lock", "startup", "socket"]


def test_lost_lock_never_runs_startup(monkeypatch):
    calls = []
    d = build()
    d._startup = lambda: calls.append("startup")

    def lost(takeover=False):
        raise SystemExit(0)

    monkeypatch.setattr(daemon_mod, "_acquire_lock", lost)
    with pytest.raises(SystemExit):
        asyncio.run(d.run())
    assert calls == []


def test_startup_exception_is_logged_not_raised(caplog):
    d = build()

    def boom():
        raise RuntimeError("settings exploded")

    d._startup = boom
    with caplog.at_level("ERROR"):
        d._run_startup()
    assert "settings exploded" in caplog.text


def test_corrupt_settings_left_untouched_and_startup_survives():
    settings = hooks.CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("{corrupt")
    d = build()
    d._run_startup()
    assert settings.read_text() == "{corrupt"


def test_startup_twice_leaves_settings_byte_identical():
    d = build()
    d._run_startup()
    first = hooks.CLAUDE_SETTINGS_PATH.read_bytes()
    d._run_startup()
    assert hooks.CLAUDE_SETTINGS_PATH.read_bytes() == first


# --- legacy autostart --------------------------------------------------------

def test_notify_autostart_passes_no_install_hooks(monkeypatch, tmp_path):
    import importlib.util
    from importlib.machinery import SourceFileLoader
    from pathlib import Path
    path = str(Path(__file__).resolve().parents[1] / "clawd-tank-notify")
    spec = importlib.util.spec_from_loader("clawd_tank_notify_t", SourceFileLoader("clawd_tank_notify_t", path))
    notify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notify)
    seen = {}
    monkeypatch.setattr(notify.subprocess, "Popen", lambda argv, **k: seen.setdefault("argv", argv))
    monkeypatch.setattr(notify, "CLAWD_DIR", tmp_path)
    monkeypatch.setattr(notify, "SOCKET_PATH", tmp_path / "never")
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    notify.start_daemon()
    assert seen["argv"] == [sys.executable, "-m", "clawd_tank_daemon.daemon", "--no-install-hooks"]
