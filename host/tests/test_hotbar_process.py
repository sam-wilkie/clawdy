"""Hotbar process lifecycle (spec: hotbar-process)."""

import json
import logging
import os
import sys

import pytest

from clawd_tank_daemon import hotbar_process
from clawd_tank_daemon.hotbar_process import HotbarProcess, find_hotbar_exe

EXE_NAME = "clawdy-hotbar.exe" if sys.platform == "win32" else "clawdy-hotbar"


class FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self.returncode = None
        self.killed = 0

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed += 1
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode


class Recorder:
    """Stands in for subprocess.Popen / subprocess.run."""

    def __init__(self):
        self.spawned = []
        self.runs = []
        self.proc = FakeProc()

    def popen(self, args, **kwargs):
        self.spawned.append((args, kwargs))
        self.proc = FakeProc()
        self.proc.returncode = None
        return self.proc

    def run(self, args, **kwargs):
        self.runs.append(args)
        if args[:3] == ["taskkill", "/F", "/PID"] and args[3] == str(self.proc.pid):
            self.proc.returncode = 1
        return None


@pytest.fixture
def rec():
    return Recorder()


@pytest.fixture
def exe(tmp_path):
    path = tmp_path / EXE_NAME
    path.write_bytes(b"")
    return str(path)


def make(rec, exe, tmp_path, image_path_of=lambda pid: None):
    return HotbarProcess(
        exe,
        popen=rec.popen,
        run=rec.run,
        image_path_of=image_path_of,
        pidfile=tmp_path / "hotbar.pid",
        log_path=tmp_path / "hotbar.log",
    )


# --- lifecycle ---------------------------------------------------------------

def test_start_spawns_with_parent_pid_and_stop_kills_it(rec, exe, tmp_path):
    hotbar = make(rec, exe, tmp_path)
    assert hotbar.start() is True
    (args, kwargs), = rec.spawned
    assert args == [exe]
    assert kwargs["env"]["CLAWDY_PARENT_PID"] == str(os.getpid())
    hotbar.stop()
    assert rec.proc.returncode is not None


def test_start_twice_spawns_once(rec, exe, tmp_path):
    hotbar = make(rec, exe, tmp_path)
    hotbar.start()
    hotbar.start()
    assert len(rec.spawned) == 1


def test_stop_twice_is_a_noop(rec, exe, tmp_path):
    hotbar = make(rec, exe, tmp_path)
    hotbar.stop()  # never started
    hotbar.start()
    hotbar.stop()
    hotbar.stop()


def test_stop_uses_taskkill_without_tree_on_windows(rec, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    hotbar = make(rec, exe, tmp_path)
    hotbar.start()
    pid = rec.proc.pid
    hotbar.stop()
    assert ["taskkill", "/F", "/PID", str(pid)] in rec.runs
    assert all("/T" not in cmd for cmd in rec.runs)


def test_no_exe_logs_a_warning_and_spawns_nothing(rec, tmp_path, caplog):
    hotbar = make(rec, None, tmp_path)
    with caplog.at_level(logging.WARNING, logger="clawd-tank.hotbar"):
        assert hotbar.start() is False
    assert rec.spawned == []
    assert "not found" in caplog.text


# --- stale cleanup -----------------------------------------------------------

def write_pidfile(tmp_path, pid, exe):
    (tmp_path / "hotbar.pid").write_text(json.dumps({"pid": pid, "exe": exe}))


def test_orphan_with_matching_image_is_killed_before_spawn(rec, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    write_pidfile(tmp_path, 777, exe)
    hotbar = make(rec, exe, tmp_path, image_path_of=lambda pid: exe)
    hotbar.start()
    assert rec.runs[0] == ["taskkill", "/F", "/PID", "777"]
    assert rec.spawned


@pytest.mark.parametrize("image", [None, "C:\\Windows\\notepad.exe"])
def test_reused_or_dead_pid_is_never_killed(rec, exe, tmp_path, monkeypatch, image):
    monkeypatch.setattr(sys, "platform", "win32")
    write_pidfile(tmp_path, 777, exe)
    hotbar = make(rec, exe, tmp_path, image_path_of=lambda pid: image)
    hotbar.start()
    assert rec.runs == []


def test_pidfile_exe_must_match_the_resolved_exe(rec, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    write_pidfile(tmp_path, 777, "C:\\other\\clawdy-hotbar.exe")
    hotbar = make(rec, exe, tmp_path, image_path_of=lambda pid: "C:\\other\\clawdy-hotbar.exe")
    hotbar.start()
    assert rec.runs == []


@pytest.mark.parametrize("content", [None, "not json", "[]", '{"pid": "x", "exe": 1}'])
def test_missing_or_corrupt_pidfile_kills_nothing(rec, exe, tmp_path, monkeypatch, content):
    monkeypatch.setattr(sys, "platform", "win32")
    if content is not None:
        (tmp_path / "hotbar.pid").write_text(content)
    hotbar = make(rec, exe, tmp_path, image_path_of=lambda pid: exe)
    hotbar.start()
    assert rec.runs == []


def test_cleanup_is_skipped_off_windows(rec, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    write_pidfile(tmp_path, 777, exe)
    hotbar = make(rec, exe, tmp_path, image_path_of=lambda pid: exe)
    hotbar.start()
    assert rec.runs == []


# --- executable lookup -------------------------------------------------------

def test_env_override_wins(tmp_path):
    override = tmp_path / "custom" / "hotbar.exe"
    override.parent.mkdir()
    override.write_bytes(b"")
    beside = tmp_path / "py"
    beside.mkdir()
    (beside / EXE_NAME).write_bytes(b"")
    found = find_hotbar_exe({"CLAWDY_HOTBAR_EXE": str(override)}, str(beside), tmp_path)
    assert found == str(override)


def test_lookup_order_next_to_python_then_repo_release(tmp_path):
    beside = tmp_path / "py"
    beside.mkdir()
    release = tmp_path / "hotbar" / "src-tauri" / "target" / "release"
    release.mkdir(parents=True)
    (release / EXE_NAME).write_bytes(b"")
    assert find_hotbar_exe({}, str(beside), tmp_path) == str(release / EXE_NAME)
    (beside / EXE_NAME).write_bytes(b"")
    assert find_hotbar_exe({}, str(beside), tmp_path) == str(beside / EXE_NAME)


def test_env_override_ignored_when_not_an_absolute_existing_file(tmp_path):
    assert find_hotbar_exe({"CLAWDY_HOTBAR_EXE": "relative.exe"}, str(tmp_path), tmp_path) is None
    missing = str(tmp_path / "gone.exe")
    assert find_hotbar_exe({"CLAWDY_HOTBAR_EXE": missing}, str(tmp_path), tmp_path) is None


# --- headless daemon ---------------------------------------------------------

def test_headless_daemon_never_builds_a_hotbar(monkeypatch):
    import clawd_tank_daemon.daemon as daemon_mod

    def boom(*a, **kw):
        raise AssertionError("headless daemon must not start the hotbar")

    monkeypatch.setattr(hotbar_process.HotbarProcess, "start", boom)
    monkeypatch.setattr(hotbar_process.HotbarProcess, "__init__", boom)
    daemon_mod._build_daemon(["--no-install-hooks"])
