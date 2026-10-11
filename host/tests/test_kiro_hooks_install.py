"""Tests for Kiro hook installation into <workspace>/.kiro/hooks/clawdy.json.

Unlike Claude/Codex (global files), Kiro Agent Hooks are per-workspace, so these
functions take a workspace folder. We own the whole clawdy.json file: install
(re)writes it, uninstall deletes it, and the user's own hooks (other files in
.kiro/hooks/) are never touched.
"""

import json

from clawd_tank_menubar import hooks
from clawd_tank_menubar.hooks import (
    install_kiro_hooks,
    uninstall_kiro_hooks,
    are_kiro_hooks_installed,
    kiro_hooks_path,
)


def test_fresh_install_writes_our_file(tmp_path):
    assert install_kiro_hooks(tmp_path) is True
    path = kiro_hooks_path(tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == "v1"
    triggers = {h["trigger"] for h in data["hooks"]}
    assert triggers == set(hooks.KIRO_TRIGGERS)
    # Every hook runs our notify with the kiro agent arg (the exact command the
    # module computed as KIRO_HOOK_COMMAND, which is HOOK_COMMAND + " kiro").
    for h in data["hooks"]:
        cmd = h["action"]["command"]
        assert cmd.endswith(" kiro")
        assert cmd == hooks.KIRO_HOOK_COMMAND


def test_file_lives_in_kiro_hooks_dir(tmp_path):
    path = kiro_hooks_path(tmp_path)
    assert path.name == "clawdy.json"
    assert path.parent == tmp_path / ".kiro" / "hooks"


def test_idempotent(tmp_path):
    install_kiro_hooks(tmp_path)
    first = kiro_hooks_path(tmp_path).read_text(encoding="utf-8")
    install_kiro_hooks(tmp_path)
    second = kiro_hooks_path(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_are_installed_true_after_install(tmp_path):
    assert are_kiro_hooks_installed(tmp_path) is False
    install_kiro_hooks(tmp_path)
    assert are_kiro_hooks_installed(tmp_path) is True


def test_are_installed_false_when_command_outdated(tmp_path):
    install_kiro_hooks(tmp_path)
    # Simulate a stale file written by a different interpreter/install path.
    path = kiro_hooks_path(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["hooks"][0]["action"]["command"] = "old-path-notify kiro"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert are_kiro_hooks_installed(tmp_path) is False


def test_uninstall_removes_our_file(tmp_path):
    install_kiro_hooks(tmp_path)
    assert kiro_hooks_path(tmp_path).exists()
    assert uninstall_kiro_hooks(tmp_path) is True
    assert not kiro_hooks_path(tmp_path).exists()


def test_uninstall_absent_file_is_noop(tmp_path):
    assert not kiro_hooks_path(tmp_path).exists()
    assert uninstall_kiro_hooks(tmp_path) is True


def test_uninstall_leaves_user_hook_files_untouched(tmp_path):
    install_kiro_hooks(tmp_path)
    # A user's own hook file sitting next to ours.
    user_file = tmp_path / ".kiro" / "hooks" / "my-own-hook.json"
    user_file.write_text('{"version":"v1","hooks":[]}', encoding="utf-8")
    uninstall_kiro_hooks(tmp_path)
    assert not kiro_hooks_path(tmp_path).exists()
    # The user's file survives.
    assert user_file.exists()
