"""Retiring the old panel must preserve hooks, other plugins and user settings."""
import json
import os
import pytest
from clawd_tank_menubar import hooks


def test_cleanup_removes_only_our_plugin_and_files():
    settings = {"model": "opus", "hooks": {"SessionStart": [{"custom": True}]},
                "env": {"OTHER": "kept", hooks.PLUGIN_DIRS_ENV:
                        os.pathsep.join(["/user/plugin", str(hooks.MOD_DIR)])}}
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings))
    hooks.MOD_DIR.mkdir(parents=True)
    (hooks.MOD_DIR / "panel.txt").write_text("retired")
    sibling = hooks.MOD_DIR.parent / "other-plugin"
    sibling.mkdir()
    assert hooks.cleanup_retired_mod()
    actual = json.loads(hooks.CLAUDE_SETTINGS_PATH.read_text())
    assert actual["hooks"] == settings["hooks"]
    assert actual["model"] == "opus"
    assert actual["env"] == {"OTHER": "kept", hooks.PLUGIN_DIRS_ENV: "/user/plugin"}
    assert not hooks.MOD_DIR.exists()
    assert sibling.is_dir()
    assert hooks.cleanup_retired_mod()  # safe to repeat at every startup


@pytest.mark.parametrize("raw", ["{broken", '{"env":{"CLAUDE_CODE_PLUGIN_DIRS":[]}}'])
def test_cleanup_leaves_invalid_settings_and_files_untouched(raw):
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text(raw)
    hooks.MOD_DIR.mkdir(parents=True)
    assert not hooks.cleanup_retired_mod()
    assert hooks.CLAUDE_SETTINGS_PATH.read_text() == raw
    assert hooks.MOD_DIR.is_dir()


def test_cleanup_rejects_an_outside_directory(tmp_path, monkeypatch):
    outside = tmp_path / "outside" / hooks.MOD_NAME
    outside.mkdir(parents=True)
    monkeypatch.setattr(hooks, "MOD_DIR", outside)
    with pytest.raises(ValueError, match="outside"):
        hooks.cleanup_retired_mod()
    assert outside.exists()
