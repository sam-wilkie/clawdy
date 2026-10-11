"""Tests for SimProcessManager."""
import asyncio
import os
import sys
import pytest
from unittest.mock import patch
from clawd_tank_daemon.sim_process import SIM_BINARY, SimProcessManager

@pytest.mark.skipif(sys.platform != "darwin",
                    reason="the .app bundle layout only exists on macOS")
def test_find_binary_in_app_bundle():
    """When running inside an .app bundle, finds sim in Contents/Resources/."""
    mgr = SimProcessManager()
    # isfile returns True only for the Resources path
    def fake_isfile(path):
        return path.endswith("Contents/Resources/clawd-tank-sim")
    with patch.object(os.path, "isfile", side_effect=fake_isfile):
        path = mgr._find_binary()
        # On macOS, NSBundle is available and returns a real bundle path
        assert path is not None
        assert path.endswith("Contents/Resources/clawd-tank-sim")

def test_find_binary_next_to_the_interpreter_uses_the_platform_suffix():
    """The sibling-of-sys.executable fallback must look for the name the build
    actually produces — clawd-tank-sim.exe on Windows, no suffix elsewhere."""
    mgr = SimProcessManager()
    seen = []
    def fake_isfile(path):
        seen.append(path)
        return path.endswith(SIM_BINARY)
    with patch.object(os.path, "isfile", side_effect=fake_isfile):
        path = mgr._find_binary()
    assert path == os.path.join(os.path.dirname(sys.executable), SIM_BINARY)
    assert SIM_BINARY.endswith(".exe") == (sys.platform == "win32")

def test_kill_stale_sims_uses_the_platform_process_killer():
    """pkill does not exist on Windows; taskkill does, and matches on the image
    name the .exe actually has."""
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        SimProcessManager.kill_stale_sims()
    command = run.call_args[0][0]
    if sys.platform == "win32":
        assert command[0] == "taskkill"
        assert SIM_BINARY in command
    else:
        assert command == ["pkill", "-9", "-f", "clawd-tank-sim"]

def test_find_binary_fallback_to_which():
    mgr = SimProcessManager()
    with patch.object(os.path, "isfile", return_value=False):
        with patch("shutil.which", return_value="/usr/local/bin/clawd-tank-sim"):
            path = mgr._find_binary()
            assert path == "/usr/local/bin/clawd-tank-sim"

def test_find_binary_returns_none():
    mgr = SimProcessManager()
    with patch.object(os.path, "isfile", return_value=False):
        with patch("shutil.which", return_value=None):
            path = mgr._find_binary()
            assert path is None

@pytest.mark.asyncio
async def test_port_probe_detects_existing():
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        mgr = SimProcessManager(port=port)
        assert await mgr._is_port_in_use() is True
    mgr2 = SimProcessManager(port=port)
    assert await mgr2._is_port_in_use() is False

def test_on_window_event_callback():
    events = []
    mgr = SimProcessManager(on_window_event=lambda e: events.append(e))
    mgr._handle_sim_event({"event": "window_hidden"})
    assert len(events) == 1
    assert events[0]["event"] == "window_hidden"


async def _spawned_args(mgr, pet=None):
    """Run start() with the process spawn and port probe faked; return (argv, env)."""
    captured = {}

    class _Proc:
        stdout = stderr = None
        returncode = None

    async def fake_exec(*args, **kw):
        captured["args"] = list(args)
        captured["env"] = kw.get("env")
        return _Proc()

    async def not_in_use():
        return False

    mgr._is_port_in_use = not_in_use
    mgr._find_binary = lambda: "sim.exe"
    mgr._find_desktop_pet = lambda: pet
    with patch("asyncio.create_subprocess_exec", fake_exec):
        await mgr.start()
    return captured["args"], captured["env"]


@pytest.mark.asyncio
async def test_normal_spawn_args_are_unchanged():
    args, env = await _spawned_args(SimProcessManager(port=1234))
    assert args == ["sim.exe", "--listen", "1234", "--hidden"]
    assert env is None
    args, _ = await _spawned_args(SimProcessManager(port=1234, start_pinned=True))
    assert args == ["sim.exe", "--listen", "1234", "--hidden", "--pinned"]


@pytest.mark.asyncio
async def test_desk_spawn_adds_desk_and_starts_visible():
    args, _ = await _spawned_args(SimProcessManager(port=1234, desk=True))
    assert args == ["sim.exe", "--listen", "1234", "--desk"]
    assert "--hidden" not in args and "--pinned" not in args


@pytest.mark.asyncio
async def test_desk_mode_prefers_the_electron_pet_on_the_same_port():
    pet = ["electron.exe", "/repo/desktop"]
    args, env = await _spawned_args(SimProcessManager(port=1234, desk=True), pet=pet)
    assert args == pet
    assert env["CLAWDY_PORT"] == "1234"


@pytest.mark.asyncio
async def test_normal_mode_never_uses_the_electron_pet():
    args, _ = await _spawned_args(SimProcessManager(port=1234), pet=["electron.exe", "/d"])
    assert args[0] == "sim.exe"


def test_find_desktop_pet_reads_the_electron_binary(tmp_path, monkeypatch):
    edir = tmp_path / "node_modules" / "electron"
    (edir / "dist").mkdir(parents=True)
    (edir / "path.txt").write_text("electron.exe", encoding="utf-8")
    (edir / "dist" / "electron.exe").write_text("")
    (tmp_path / "main.js").write_text("")
    monkeypatch.setenv("CLAWDY_DESKTOP_DIR", str(tmp_path))
    monkeypatch.delenv("CLAWDY_DESKTOP_PET", raising=False)
    assert SimProcessManager()._find_desktop_pet() == [
        str(edir / "dist" / "electron.exe"), str(tmp_path)]
    monkeypatch.setenv("CLAWDY_DESKTOP_PET", "0")
    assert SimProcessManager()._find_desktop_pet() is None


def test_find_desktop_pet_none_without_dependencies(tmp_path, monkeypatch):
    (tmp_path / "main.js").write_text("")
    monkeypatch.setenv("CLAWDY_DESKTOP_DIR", str(tmp_path))
    monkeypatch.delenv("CLAWDY_DESKTOP_PET", raising=False)
    assert SimProcessManager()._find_desktop_pet() is None
