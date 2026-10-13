"""Tests for SimProcessManager."""
import asyncio
import os
import sys
import pytest
from pathlib import Path
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


def _fake_frozen_install(root, monkeypatch, *, with_main=True, with_path_txt=True):
    """Lay out a frozen PyInstaller onedir (host/dist/MargaritaTank/) and point
    sys at it. Returns the bundled desktop/ folder."""
    app_dir = root / "MargaritaTank"
    pet = app_dir / "desktop"
    edir = pet / "node_modules" / "electron"
    (edir / "dist").mkdir(parents=True)
    (edir / "dist" / "electron.exe").write_text("")
    if with_path_txt:
        (edir / "path.txt").write_text("electron.exe", encoding="utf-8")
    if with_main:
        (pet / "main.js").write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app_dir / "MargaritaTank.exe"))
    monkeypatch.delenv("CLAWDY_DESKTOP_DIR", raising=False)
    monkeypatch.delenv("CLAWDY_DESKTOP_PET", raising=False)
    return pet


def _no_repo_checkout(monkeypatch, tmp_path):
    """Point __file__ at a checkout that does not exist, so the repo desktop/
    fallback resolves to nothing and a None result is unambiguous."""
    from clawd_tank_daemon import sim_process
    monkeypatch.setattr(sim_process, "__file__", str(
        Path(tmp_path) / "no-checkout" / "clawd_tank_daemon" / "sim_process.py"))


def test_find_desktop_pet_resolves_the_pet_bundled_next_to_the_frozen_exe(tmp_path, monkeypatch):
    """The Windows release is a flat onedir, so the pet ships one level below
    the exe — the same place _find_binary() looks for the simulator."""
    pet = _fake_frozen_install(tmp_path, monkeypatch)
    _no_repo_checkout(monkeypatch, tmp_path)
    assert SimProcessManager()._find_desktop_pet() == [
        str(pet / "node_modules" / "electron" / "dist" / "electron.exe"), str(pet)]


def test_find_desktop_pet_ignores_an_exe_adjacent_pet_when_not_frozen(tmp_path, monkeypatch):
    """Source checkouts must keep using the repo's desktop/, or a dev would
    launch a stale pet from whatever sits next to their interpreter."""
    pet = _fake_frozen_install(tmp_path, monkeypatch)
    monkeypatch.delattr(sys, "frozen", raising=False)
    result = SimProcessManager()._find_desktop_pet()
    assert not result or result[1] != str(pet)


def test_find_desktop_pet_env_dir_wins_over_the_frozen_bundle(tmp_path, monkeypatch):
    _fake_frozen_install(tmp_path, monkeypatch)
    _no_repo_checkout(monkeypatch, tmp_path)
    other = tmp_path / "elsewhere"
    edir = other / "node_modules" / "electron"
    (edir / "dist").mkdir(parents=True)
    (edir / "path.txt").write_text("electron.exe", encoding="utf-8")
    (edir / "dist" / "electron.exe").write_text("")
    (other / "main.js").write_text("")
    monkeypatch.setenv("CLAWDY_DESKTOP_DIR", str(other))
    assert SimProcessManager()._find_desktop_pet() == [
        str(edir / "dist" / "electron.exe"), str(other)]


def test_find_desktop_pet_disabled_beats_the_frozen_bundle(tmp_path, monkeypatch):
    _fake_frozen_install(tmp_path, monkeypatch)
    _no_repo_checkout(monkeypatch, tmp_path)
    monkeypatch.setenv("CLAWDY_DESKTOP_PET", "0")
    assert SimProcessManager()._find_desktop_pet() is None


def test_find_desktop_pet_none_when_the_frozen_bundle_has_no_sources(tmp_path, monkeypatch):
    _fake_frozen_install(tmp_path, monkeypatch, with_main=False)
    _no_repo_checkout(monkeypatch, tmp_path)
    assert SimProcessManager()._find_desktop_pet() is None


def test_find_desktop_pet_none_when_the_frozen_runtime_is_missing(tmp_path, monkeypatch):
    _fake_frozen_install(tmp_path, monkeypatch, with_path_txt=False)
    _no_repo_checkout(monkeypatch, tmp_path)
    assert SimProcessManager()._find_desktop_pet() is None


@pytest.mark.asyncio
async def test_client_is_marked_desktop_pet_only_when_the_electron_pet_runs():
    """The daemon sends the pet-only "waiting_reply" animation solely to a
    client flagged as the Electron desktop pet; the SDL2 window never is."""
    from clawd_tank_daemon.sim_client import SimClient

    async def client_of(mgr, pet=None):
        async def fake_exec(*args, **kw):
            class _Proc:
                stdout = stderr = None
                returncode = None
            return _Proc()

        async def not_in_use():
            return False

        mgr._is_port_in_use = not_in_use
        mgr._find_binary = lambda: "sim.exe"
        mgr._find_desktop_pet = lambda: pet
        with patch("asyncio.create_subprocess_exec", fake_exec):
            return await mgr.start()

    pet = ["electron.exe", "/repo/desktop"]
    assert (await client_of(SimProcessManager(port=1234, desk=True), pet)).desktop_pet is True
    assert (await client_of(SimProcessManager(port=1234, desk=True))).desktop_pet is False
    assert (await client_of(SimProcessManager(port=1234), pet)).desktop_pet is False
    assert SimClient().desktop_pet is False


# --- Killing the simulator / desktop pet on quit ------------------------------


class _FakeProc:
    """Stands in for asyncio.subprocess.Process; records kill() calls."""

    def __init__(self, pid=4321):
        self.pid = pid
        self.returncode = None
        self.kill_calls = 0

    def kill(self):
        self.kill_calls += 1

    async def wait(self):
        self.returncode = -9


def _as_platform(name):
    import types
    return patch("clawd_tank_daemon.sim_process.sys", types.SimpleNamespace(platform=name))


def test_kill_sync_on_windows_kills_the_whole_process_tree_by_pid():
    """Electron spawns GPU/renderer children; TerminateProcess on the main exe
    leaves them behind. The tree kill must target OUR pid, never an image name
    (other Electron apps run on the same machine)."""
    mgr = SimProcessManager()
    mgr._process = _FakeProc(pid=4321)
    with _as_platform("win32"), patch("subprocess.run") as run:
        mgr.kill_sync()
    command = run.call_args[0][0]
    assert command[0] == "taskkill"
    assert "/F" in command and "/T" in command
    assert command[command.index("/PID") + 1] == "4321"
    assert "/IM" not in command
    assert not any("electron" in part.lower() for part in command)


def test_kill_sync_off_windows_keeps_the_plain_process_kill():
    mgr = SimProcessManager()
    proc = _FakeProc()
    mgr._process = proc
    with _as_platform("linux"), patch("subprocess.run") as run:
        mgr.kill_sync()
    assert proc.kill_calls == 1
    run.assert_not_called()


def test_kill_sync_is_a_noop_without_a_live_process():
    mgr = SimProcessManager()
    with _as_platform("win32"), patch("subprocess.run") as run:
        mgr.kill_sync()  # never started
        dead = _FakeProc()
        dead.returncode = 0
        mgr._process = dead
        mgr.kill_sync()  # already exited
    run.assert_not_called()


def test_kill_sync_survives_a_missing_taskkill():
    mgr = SimProcessManager()
    proc = _FakeProc()
    mgr._process = proc
    with _as_platform("win32"), patch("subprocess.run", side_effect=FileNotFoundError):
        mgr.kill_sync()  # must not raise
    assert proc.kill_calls == 1  # falls back to killing the main process


@pytest.mark.asyncio
async def test_async_kill_on_windows_also_kills_the_tree():
    mgr = SimProcessManager()
    mgr._process = _FakeProc(pid=777)
    with _as_platform("win32"), patch("subprocess.run") as run:
        await mgr.kill()
    command = run.call_args[0][0]
    assert command[command.index("/PID") + 1] == "777"
    assert mgr._process is None
