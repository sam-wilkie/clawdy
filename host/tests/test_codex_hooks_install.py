"""Tests for Codex hook installation into ~/.codex/hooks.json.

install_codex_hooks() must MERGE our groups without clobbering the user's own
Codex hooks, be idempotent, and uninstall_codex_hooks() must remove only ours.
"""

import json
import ntpath

import pytest

from clawd_tank_menubar import hooks
from clawd_tank_menubar.hooks import install_codex_hooks, uninstall_codex_hooks


@pytest.fixture(autouse=True)
def codex_path(tmp_path, monkeypatch):
    p = tmp_path / "hooks.json"
    monkeypatch.setattr(hooks, "CODEX_HOOKS_PATH", p)
    return p


def _read(p) -> dict:
    return json.loads(p.read_text())


def _our_count(data: dict, event: str) -> int:
    n = 0
    for group in data.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            if hooks._command_is_ours(h.get("command", "")):
                n += 1
    return n


def test_fresh_install_writes_our_groups(codex_path):
    assert install_codex_hooks() is True
    data = _read(codex_path)
    # Every Codex event we manage has exactly one of our groups.
    for event in hooks.CODEX_HOOKS_CONFIG:
        assert _our_count(data, event) == 1, event
    # The command carries the codex agent arg.
    cmd = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert cmd.endswith(" codex")


def test_idempotent(codex_path):
    install_codex_hooks()
    install_codex_hooks()
    data = _read(codex_path)
    for event in hooks.CODEX_HOOKS_CONFIG:
        assert _our_count(data, event) == 1, event


def test_preserves_user_groups(codex_path):
    user = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-script.sh"}]}
            ],
            "CustomEvent": [
                {"hooks": [{"type": "command", "command": "user-thing"}]}
            ],
        }
    }
    codex_path.write_text(json.dumps(user))
    install_codex_hooks()
    data = _read(codex_path)
    # User's PreToolUse group survives alongside ours.
    pre_cmds = [h["command"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert "my-own-script.sh" in pre_cmds
    assert any(c.endswith(" codex") for c in pre_cmds)
    # A user event we don't manage is untouched.
    assert data["hooks"]["CustomEvent"][0]["hooks"][0]["command"] == "user-thing"


def test_uninstall_removes_only_ours(codex_path):
    user = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-script.sh"}]}
            ],
        }
    }
    codex_path.write_text(json.dumps(user))
    install_codex_hooks()
    assert uninstall_codex_hooks() is True
    data = _read(codex_path)
    pre_cmds = [h["command"] for g in data["hooks"].get("PreToolUse", []) for h in g["hooks"]]
    # Ours gone, user's kept.
    assert "my-own-script.sh" in pre_cmds
    assert not any(c.endswith(" codex") for c in pre_cmds)
    # Events that held only our groups are dropped entirely.
    assert "SessionStart" not in data.get("hooks", {})


def test_uninstall_absent_file_is_noop(codex_path):
    assert not codex_path.exists()
    assert uninstall_codex_hooks() is True


def test_unparseable_file_left_untouched(codex_path):
    codex_path.write_text("{ not json")
    assert install_codex_hooks() is False
    # The bad file is left exactly as-is.
    assert codex_path.read_text() == "{ not json"


# --- Windows command shape: Codex runs hooks via cmd /c or powershell -Command,
# and the double-quoted form exits 1 under both, so no-space paths go unquoted.

PY = r"C:\py\python.exe"


def test_codex_command_unquoted_without_spaces():
    cmd = hooks.build_codex_hook_command("win32", False, PY, r"C:\clawd\clawd-tank-notify.py")
    assert cmd == r"C:\py\python.exe C:\clawd\clawd-tank-notify.py codex"


def test_codex_command_uses_console_python_for_windowed_tray():
    assert hooks.build_codex_hook_command(
        "win32", False, r"C:\py\pythonw.exe", r"C:\clawd\clawd-tank-notify.py"
    ) == r"C:\py\python.exe C:\clawd\clawd-tank-notify.py codex"


def test_codex_command_quoted_fallback_with_spaces():
    cmd = hooks.build_codex_hook_command(
        "win32", False, r"C:\Program Files\py\python.exe", r"C:\clawd\clawd-tank-notify.py")
    assert cmd == r'"C:\Program Files\py\python.exe" "C:\clawd\clawd-tank-notify.py" codex'
    cmd = hooks.build_codex_hook_command("win32", False, PY, r"C:\my dir\clawd-tank-notify.py")
    assert cmd == r'"C:\py\python.exe" "C:\my dir\clawd-tank-notify.py" codex'


def test_codex_command_frozen_exe():
    cmd = hooks.build_codex_hook_command("win32", True, r"C:\App\MargaritaTank.exe", None)
    assert cmd == ntpath.join("C:/App".replace("/", chr(92)), hooks.NOTIFY_EXE_NAME) + " codex"
    cmd = hooks.build_codex_hook_command("win32", True, r"C:\My App\MargaritaTank.exe", None)
    assert cmd == '"' + ntpath.join("C:/My App".replace("/", chr(92)), hooks.NOTIFY_EXE_NAME) + '" codex'


def test_codex_command_posix_unchanged():
    assert hooks.build_codex_hook_command(
        "linux", False, "/usr/bin/python3", "/home/u/.clawd-tank/clawd-tank-notify"
    ) == "/home/u/.clawd-tank/clawd-tank-notify codex"


def test_ownership_recognises_quoted_and_unquoted_codex_commands():
    script = hooks.NOTIFY_SCRIPT_PATH
    rx = hooks.build_our_command_re("win32", script)
    assert rx.match(f'"{PY}" "{script}" codex')
    assert rx.match(f"{PY} {script} codex")
    assert rx.match(ntpath.join("C:/App".replace("/", chr(92)), hooks.NOTIFY_EXE_NAME) + " codex")
    assert not rx.match(f"cat {script}")
    assert not rx.match(f"{PY} other.py {script}")


def _win_codex_commands(monkeypatch):
    script = hooks.NOTIFY_SCRIPT_PATH
    monkeypatch.setattr(hooks, "_OUR_COMMAND_RE", hooks.build_our_command_re("win32", script))
    return f'"{PY}" "{script}" codex', f"{PY} {script} codex"


def test_upgrade_from_old_quoted_command_replaces_not_duplicates(codex_path, monkeypatch):
    old, new = _win_codex_commands(monkeypatch)
    monkeypatch.setattr(hooks, "CODEX_HOOKS_CONFIG", hooks.build_codex_hooks_config(new))
    codex_path.write_text(json.dumps({"hooks": hooks.build_codex_hooks_config(old)}))
    assert install_codex_hooks() is True
    data = _read(codex_path)
    for event in hooks.CODEX_HOOKS_CONFIG:
        cmds = [h["command"] for g in data["hooks"][event] for h in g["hooks"]]
        assert cmds == [new], event


def test_uninstall_removes_both_command_forms(codex_path, monkeypatch):
    old, new = _win_codex_commands(monkeypatch)
    cfg = {"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": old}]},
        {"hooks": [{"type": "command", "command": new}]},
        {"hooks": [{"type": "command", "command": "mine.sh"}]},
    ]}}
    codex_path.write_text(json.dumps(cfg))
    assert uninstall_codex_hooks() is True
    assert _read(codex_path)["hooks"]["Stop"] == [
        {"hooks": [{"type": "command", "command": "mine.sh"}]}]
