"""Tests for OpenCode plugin installation into ~/.config/opencode/opencode.json
(macOS/Linux) and %APPDATA%\\opencode\\opencode.json (Windows).

install_opencode_hooks() must MERGE our plugin entry into the user's
opencode.json without clobbering their own plugin entries, be idempotent,
and uninstall_opencode_hooks() must remove only ours.

Mirrors the structure of `test_codex_hooks_install.py`. Tests use
monkeypatching on the module-level path constants and the bundled plugin
source constant — the actual plugin file lands in PR2; for PR1 the tests
swap in a small text fixture so install/uninstall can copy it.
"""

import json
import sys
from pathlib import Path

import pytest

from clawd_tank_menubar import hooks
from clawd_tank_menubar.hooks import (
    install_opencode_hooks,
    uninstall_opencode_hooks,
    are_opencode_hooks_installed,
)


# --- Fixtures: redirect every module-level path to tmp_path -------------------

@pytest.fixture
def opencode_paths(tmp_path, monkeypatch):
    """Point OPENCODE_CONFIG_PATH / OPENCODE_PLUGIN_PATH / OPENCODE_PLUGIN_SOURCE
    under tmp_path so tests don't touch the user's real ~/.config or %APPDATA%.

    Also write a stub plugin source file the installer can read.
    """
    config_dir = tmp_path / "opencode"
    plugins_dir = config_dir / "plugins"
    config_path = config_dir / "opencode.json"
    plugin_path = plugins_dir / "clawd-tank.js"
    source_path = tmp_path / "clawd-tank-opencode.js"
    source_path.write_text("// stub OpenCode plugin for PR1 tests\n", encoding="utf-8")

    monkeypatch.setattr(hooks, "OPENCODE_CONFIG_PATH", config_path)
    monkeypatch.setattr(hooks, "OPENCODE_PLUGIN_PATH", plugin_path)
    monkeypatch.setattr(hooks, "OPENCODE_PLUGIN_SOURCE", source_path)
    return {
        "config_path": config_path,
        "plugin_path": plugin_path,
        "source_path": source_path,
        "config_dir": config_dir,
        "plugins_dir": plugins_dir,
    }


def _our_plugin_entry(settings: dict) -> str:
    """The exact plugin-file URL string the installer writes into
    opencode.json's `plugin` array."""
    return hooks._opencode_plugin_entry()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- install_opencode_hooks --------------------------------------------------

def test_install_writes_plugin_file_and_merges_entry(opencode_paths):
    """Fresh install: copy the plugin file to the target location AND add our
    entry to opencode.json's plugin array."""
    assert install_opencode_hooks() is True
    p = opencode_paths
    # 1. Plugin file exists at the target and matches the bundled source.
    assert p["plugin_path"].is_file()
    assert p["plugin_path"].read_text(encoding="utf-8") == p["source_path"].read_text(encoding="utf-8")
    # 2. opencode.json has our plugin entry.
    data = _read_json(p["config_path"])
    assert "plugin" in data
    assert _our_plugin_entry(data) in data["plugin"]


def test_install_backs_up_existing_config(opencode_paths):
    """When opencode.json already exists, install copies the original to
    opencode.json.clawd-tank.bak before merging our entry. The backup is what
    uninstall restores from byte-for-byte."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    original = '{"theme":"dark","plugin":["file:///user/other.js"]}'
    p["config_path"].write_text(original, encoding="utf-8")
    assert install_opencode_hooks() is True
    backup = p["config_path"].with_name(p["config_path"].name + hooks.OPENCODE_BACKUP_SUFFIX)
    assert backup.is_file()
    # The backup holds the EXACT pre-install bytes — including the user's own
    # plugin entries — so uninstall can restore without us tracking the diff.
    assert backup.read_text(encoding="utf-8") == original


def test_install_creates_opencode_json_when_absent(opencode_paths):
    """If opencode.json doesn't exist yet, install creates it (with just our
    entry — no other fields)."""
    p = opencode_paths
    assert not p["config_path"].exists()
    install_opencode_hooks()
    assert p["config_path"].is_file()
    data = _read_json(p["config_path"])
    assert data.get("plugin") == [_our_plugin_entry(data)]


def test_install_is_idempotent(opencode_paths):
    """A second install with the entry already present is a no-op."""
    install_opencode_hooks()
    install_opencode_hooks()
    data = _read_json(opencode_paths["config_path"])
    # Exactly one of our entries, not two.
    matching = [e for e in data.get("plugin", []) if hooks._is_our_opencode_plugin(e)]
    assert len(matching) == 1


def test_install_preserves_user_plugin_entries(opencode_paths):
    """User's plugin entries (other than ours) survive the install."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    p["config_path"].write_text(json.dumps({"plugin": ["file:///user/other-plugin.js"]}))
    install_opencode_hooks()
    data = _read_json(p["config_path"])
    assert "file:///user/other-plugin.js" in data["plugin"]
    assert _our_plugin_entry(data) in data["plugin"]


def test_install_preserves_user_non_plugin_fields(opencode_paths):
    """Top-level non-`plugin` keys in opencode.json (theme, telemetry, ...) are
    untouched."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    p["config_path"].write_text(json.dumps({"theme": "dark", "telemetry": False}))
    install_opencode_hooks()
    data = _read_json(p["config_path"])
    assert data["theme"] == "dark"
    assert data["telemetry"] is False
    assert _our_plugin_entry(data) in data["plugin"]


def test_install_refuses_when_opencode_json_unparseable(opencode_paths):
    """If opencode.json exists but is not valid JSON, install refuses and
    leaves the file byte-for-byte unchanged (mirrors the Codex installer's
    `test_unparseable_file_left_untouched` rule)."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    p["config_path"].write_text("{ not json", encoding="utf-8")
    assert install_opencode_hooks() is False
    # File untouched (not even backed up — we never got that far).
    assert p["config_path"].read_text() == "{ not json"
    # Plugin file not created.
    assert not p["plugin_path"].exists()


def test_install_refuses_when_plugin_source_missing(opencode_paths, monkeypatch):
    """If the bundled plugin source is missing (PR1: it lands in PR2),
    install refuses with a clear log message — no partial state."""
    p = opencode_paths
    p["source_path"].unlink()
    assert install_opencode_hooks() is False
    # No opencode.json written, no plugin file copied.
    assert not p["config_path"].exists()
    assert not p["plugin_path"].exists()


# --- uninstall_opencode_hooks -----------------------------------------------

def test_uninstall_removes_plugin_file_and_restores_backup(opencode_paths):
    """When install backed up an existing opencode.json, uninstall restores
    the original byte-for-byte from the backup."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    original = '{"theme":"dark"}'
    p["config_path"].write_text(original, encoding="utf-8")
    install_opencode_hooks()
    backup = p["config_path"].with_name(p["config_path"].name + hooks.OPENCODE_BACKUP_SUFFIX)
    assert backup.is_file()
    assert uninstall_opencode_hooks() is True
    # Plugin file gone
    assert not p["plugin_path"].exists()
    # opencode.json restored byte-for-byte from backup
    assert p["config_path"].read_text(encoding="utf-8") == original
    # Backup file deleted
    assert not backup.exists()


def test_uninstall_when_never_installed_is_noop(opencode_paths):
    """No plugin file, no backup, no opencode.json -> uninstall returns True
    and does not raise."""
    assert not opencode_paths["plugin_path"].exists()
    assert uninstall_opencode_hooks() is True


def test_uninstall_preserves_user_plugin_entries(opencode_paths):
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    p["config_path"].write_text(json.dumps({"plugin": ["file:///user/other.js"]}))
    install_opencode_hooks()
    assert uninstall_opencode_hooks() is True
    data = _read_json(p["config_path"])
    assert "file:///user/other.js" in data["plugin"]
    # Our entry is gone.
    assert not any(hooks._is_our_opencode_plugin(e) for e in data.get("plugin", []))


def test_uninstall_idempotent(opencode_paths):
    """Calling uninstall twice in a row returns True both times."""
    install_opencode_hooks()
    assert uninstall_opencode_hooks() is True
    assert uninstall_opencode_hooks() is True


def test_uninstall_removes_only_our_entries_among_user_others(opencode_paths):
    """If the plugin array holds BOTH ours and the user's entries, uninstall
    removes ours and leaves the user's untouched."""
    p = opencode_paths
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    # Manually craft an opencode.json with a user entry AND one of ours.
    # We install first (which writes a clean file) then patch in the user
    # entry directly, then uninstall.
    install_opencode_hooks()
    data = _read_json(p["config_path"])
    data["plugin"].append("file:///user/other.js")
    p["config_path"].write_text(json.dumps(data))
    assert uninstall_opencode_hooks() is True
    data = _read_json(p["config_path"])
    assert "file:///user/other.js" in data["plugin"]
    assert not any(hooks._is_our_opencode_plugin(e) for e in data.get("plugin", []))


# --- are_opencode_hooks_installed --------------------------------------------

def test_are_installed_false_when_no_plugin_file(opencode_paths):
    assert are_opencode_hooks_installed() is False


def test_are_installed_false_when_no_config_entry(opencode_paths):
    """Plugin file exists but opencode.json has no plugin entry -> False."""
    p = opencode_paths
    p["plugin_path"].parent.mkdir(parents=True, exist_ok=True)
    p["plugin_path"].write_text("dummy")
    p["config_path"].parent.mkdir(parents=True, exist_ok=True)
    p["config_path"].write_text(json.dumps({"theme": "dark"}))
    assert are_opencode_hooks_installed() is False


def test_are_installed_true_after_install(opencode_paths):
    install_opencode_hooks()
    assert are_opencode_hooks_installed() is True


def test_are_installed_false_after_uninstall(opencode_paths):
    install_opencode_hooks()
    uninstall_opencode_hooks()
    assert are_opencode_hooks_installed() is False


# --- resolve_plugin_source / platform path resolution -----------------------

def test_opencode_plugin_entry_is_file_url(opencode_paths):
    """The plugin entry written into opencode.json is a file:// URL pointing
    at the install target — OpenCode's loader expects this form."""
    import os
    from urllib.parse import urlparse, unquote
    p = opencode_paths
    entry = hooks._opencode_plugin_entry()
    assert entry.startswith("file://")
    parsed = urlparse(entry)
    # Windows URL: `file:///C:/...` -> path is `/C:/...`; POSIX URL:
    # `file:///abs/path` -> path is `/abs/path`. Strip the leading slash for
    # Windows drive letters so normpath compares them correctly.
    url_path = unquote(parsed.path)
    if sys.platform == "win32" and url_path.startswith("/") and len(url_path) > 2 and url_path[2] == ":":
        url_path = url_path[1:]
    expected = str(p["plugin_path"].resolve())
    assert os.path.normpath(url_path) == os.path.normpath(expected)


@pytest.mark.parametrize("platform_name,expected_subpath", [
    ("darwin", ".config/opencode/opencode.json"),
    ("linux", ".config/opencode/opencode.json"),
    ("win32", "AppData/Roaming/opencode/opencode.json"),
])
def test_opencode_config_path_platform(platform_name, expected_subpath,
                                       monkeypatch, tmp_path):
    """The config path follows XDG on POSIX and %APPDATA% on Windows. POSIX
    uses ~/.config/opencode/; Windows uses %APPDATA%/opencode/ (the roaming
    profile path that matches VS Code, Slack, etc.)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setattr(sys, "platform", platform_name)
    # On Windows the implementation reads APPDATA first; clear it so the
    # Path.home() override is what we test against.
    monkeypatch.delenv("APPDATA", raising=False)
    path = hooks._opencode_config_path()
    expected = fake_home / expected_subpath
    assert path == expected