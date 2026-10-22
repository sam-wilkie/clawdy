"""T4: Pi extension installer (S4). Writes only our two files under <agent-dir>/extensions."""

from pathlib import Path

import clawd_tank_menubar.hooks as hooks


def test_install_writes_extension_and_command(tmp_path):
    assert hooks.install_pi_hooks(agent_dir=tmp_path) is True
    ext = tmp_path / "extensions" / "clawd-tank.js"
    assert ext.is_file()
    assert (tmp_path / "extensions" / "clawd-tank.command").read_text(encoding="utf-8").strip()


def test_install_is_detected_then_uninstall_removes_only_ours(tmp_path):
    other = tmp_path / "extensions" / "other.js"
    other.parent.mkdir(parents=True)
    other.write_text("keep me", encoding="utf-8")
    hooks.install_pi_hooks(agent_dir=tmp_path)
    assert hooks.are_pi_hooks_installed(agent_dir=tmp_path) is True
    assert hooks.uninstall_pi_hooks(agent_dir=tmp_path) is True
    assert not (tmp_path / "extensions" / "clawd-tank.js").exists()
    assert not (tmp_path / "extensions" / "clawd-tank.command").exists()
    assert other.read_text(encoding="utf-8") == "keep me"
    assert hooks.are_pi_hooks_installed(agent_dir=tmp_path) is False


def test_extension_source_ships_in_repo_and_calls_notify_as_pi():
    src = (Path(__file__).resolve().parents[1] / "pi-extension" / "clawd-tank.js").read_text(encoding="utf-8")
    assert "tool_call" in src and "agent_start" in src and "session_shutdown" in src
    assert '"permission"' not in src  # Pi runs tools freely; no bubble per bash/write/edit
    assert '"pi"' in src
