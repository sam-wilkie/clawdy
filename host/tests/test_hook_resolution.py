"""Hook executable resolution (spec: hook-command-resolution)."""

import json
import ntpath
import sys

import pytest

import clawd_tank_menubar.hooks as hooks

WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="validates Windows paths on disk")


# --- golden equality (current layouts must not change) -----------------------

FROZEN = r"C:\Program Files\Margarita Tank\MargaritaTank.exe"
SCRIPT = r"C:\Users\a b\.clawd-tank\clawd-tank-notify"


def test_golden_frozen_windows():
    exe = hooks.resolve_hook_executable("win32", True, FROZEN, {})
    assert hooks.build_hook_command("win32", True, exe, SCRIPT) == \
        r'"C:\Program Files\Margarita Tank\margarita-notify.exe"'
    assert hooks.build_statusline_command("win32", True, exe, SCRIPT) == \
        r'"C:\Program Files\Margarita Tank\margarita-statusline.exe"'


def test_golden_dev_windows_and_pythonw():
    py = r"C:\Py Dir\python.exe"
    assert hooks.build_hook_command(
        "win32", False, hooks.resolve_hook_executable("win32", False, py, {}), SCRIPT
    ) == rf'"{py}" "{SCRIPT}"'
    assert hooks.build_hook_command(
        "win32", False, hooks.resolve_hook_executable("win32", False, r"C:\Py Dir\pythonw.exe", {}), SCRIPT
    ) == rf'"{py}" "{SCRIPT}"'
    assert hooks.build_statusline_command("win32", False, py, SCRIPT) == rf'"{py}" "{SCRIPT}"'


def test_golden_posix_unchanged():
    exe = hooks.resolve_hook_executable("darwin", True, "/Applications/M.app/python", {})
    assert exe == "/Applications/M.app/python"
    assert hooks.build_hook_command("darwin", True, exe, "/home/a b/notify") == "/home/a b/notify"
    assert hooks.build_statusline_command("darwin", True, exe, "/home/a b/s.sh") == "/bin/sh '/home/a b/s.sh'"


# --- explicit location -------------------------------------------------------

@pytest.fixture
def exe_dir(tmp_path):
    d = tmp_path / "side car"
    d.mkdir()
    (d / hooks.NOTIFY_EXE_NAME).write_bytes(b"")
    (d / hooks.STATUSLINE_EXE_NAME).write_bytes(b"")
    return d


@WIN_ONLY
def test_env_override_drives_notify_and_statusline(exe_dir):
    exe = hooks.resolve_hook_executable("win32", True, FROZEN, {"CLAWD_TANK_HOOK_EXE_DIR": str(exe_dir)})
    assert exe == ntpath.join(str(exe_dir), hooks.NOTIFY_EXE_NAME)
    assert hooks.build_hook_command("win32", True, exe, SCRIPT) == f'"{exe_dir}\\margarita-notify.exe"'
    assert hooks.build_statusline_command("win32", True, exe, SCRIPT) == f'"{exe_dir}\\margarita-statusline.exe"'


@WIN_ONLY
def test_invalid_overrides_are_ignored_with_warning(tmp_path, exe_dir, caplog):
    only_notify = tmp_path / "half"
    only_notify.mkdir()
    (only_notify / hooks.NOTIFY_EXE_NAME).write_bytes(b"")
    for bad in ("relative\\dir", str(tmp_path / "missing"), str(only_notify), str(exe_dir) + '"&calc'):
        caplog.clear()
        with caplog.at_level("WARNING"):
            assert hooks.resolve_hook_executable(
                "win32", True, FROZEN, {"CLAWD_TANK_HOOK_EXE_DIR": bad}) == FROZEN
        assert "CLAWD_TANK_HOOK_EXE_DIR" in caplog.text


def test_override_never_applies_off_windows_or_unfrozen(exe_dir):
    env = {"CLAWD_TANK_HOOK_EXE_DIR": str(exe_dir)}
    assert hooks.resolve_hook_executable("darwin", True, "/x/py", env) == "/x/py"
    assert hooks.resolve_hook_executable("win32", False, r"C:\Py\python.exe", env) == r"C:\Py\python.exe"


# --- ensure_hooks_current ----------------------------------------------------

def read(p):
    return p.read_bytes() if p.exists() else None


def test_missing_frozen_exe_leaves_settings_untouched(tmp_path):
    settings = hooks.CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"hooks": {}, "theme": "dark"}))
    before = read(settings)
    gone = str(tmp_path / "gone" / "MargaritaTank.exe")
    assert hooks.ensure_hooks_current("win32", True, gone) is False
    assert read(settings) == before


def test_installs_then_second_run_writes_nothing():
    assert hooks.ensure_hooks_current() is True
    settings = hooks.CLAUDE_SETTINGS_PATH
    first, mtime = read(settings), settings.stat().st_mtime_ns
    assert hooks.ensure_hooks_current() is True
    assert read(settings) == first and settings.stat().st_mtime_ns == mtime


def test_stale_managed_hook_is_repointed_and_user_hooks_survive():
    settings = hooks.CLAUDE_SETTINGS_PATH
    settings.parent.mkdir(parents=True, exist_ok=True)
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-linter"}]}
    if hooks._OUR_COMMAND_RE is None:
        pytest.skip("only Windows prunes commands left by another interpreter")
    stale_cmd = f'"C:\\old\\python.exe" "{hooks.NOTIFY_SCRIPT_PATH}"'
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [
        user, {"hooks": [{"type": "command", "command": stale_cmd}]}]}}))
    assert hooks.ensure_hooks_current() is True
    data = json.loads(read(settings))
    cmds = [h["command"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert stale_cmd not in cmds and hooks.HOOK_COMMAND in cmds
    assert user in data["hooks"]["PreToolUse"]


def test_override_rejects_dir_without_a_drive(monkeypatch):
    monkeypatch.setattr(hooks.os.path, "isfile", lambda p: True)
    for bad in ("\\rooted\\only", "C:relative"):
        assert hooks.resolve_hook_executable(
            "win32", True, FROZEN, {"CLAWD_TANK_HOOK_EXE_DIR": bad}) == FROZEN
    ok = "D:\\Side Car"
    assert hooks.resolve_hook_executable(
        "win32", True, FROZEN, {"CLAWD_TANK_HOOK_EXE_DIR": ok}) == ok + "\\margarita-notify.exe"
