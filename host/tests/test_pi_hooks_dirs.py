"""Pi extension install targets: Gentle Shell's agent dir plus a plain Pi's ~/.pi/agent."""
import pytest

from clawd_tank_menubar import hooks


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    return tmp_path


def installed(agent):
    ext = agent / "extensions"
    return (ext / hooks.PI_EXTENSION_NAME).is_file() and (ext / hooks.PI_COMMAND_NAME).is_file()


def test_gentle_shell_only_when_plain_pi_has_no_agent_dir(home):
    assert hooks.install_pi_hooks() is True
    assert installed(home / ".gentle-shell" / "agent")
    assert not (home / ".pi").exists()


def test_plain_pi_agent_dir_gets_the_extension_too(home):
    (home / ".pi" / "agent").mkdir(parents=True)
    assert hooks.install_pi_hooks() is True
    for agent in (home / ".gentle-shell" / "agent", home / ".pi" / "agent"):
        assert installed(agent)
        copied = (agent / "extensions" / hooks.PI_EXTENSION_NAME).read_bytes()
        assert copied == hooks.PI_EXTENSION_SOURCE.read_bytes()
        assert (agent / "extensions" / hooks.PI_COMMAND_NAME).read_text(encoding="utf-8") == hooks.HOOK_COMMAND


def test_detection_needs_every_target(home):
    (home / ".pi" / "agent").mkdir(parents=True)
    hooks.install_pi_hooks(agent_dir=home / ".gentle-shell" / "agent")
    assert hooks.are_pi_hooks_installed() is False  # plain Pi's dir is still missing it
    hooks.install_pi_hooks()
    assert hooks.are_pi_hooks_installed() is True


def test_uninstall_clears_every_target_and_keeps_other_files(home):
    plain = home / ".pi" / "agent"
    (plain / "extensions").mkdir(parents=True)
    (plain / "extensions" / "mine.js").write_text("// not ours", encoding="utf-8")
    hooks.install_pi_hooks()
    assert hooks.uninstall_pi_hooks() is True
    assert not installed(home / ".gentle-shell" / "agent") and not installed(plain)
    assert (plain / "extensions" / "mine.js").read_text(encoding="utf-8") == "// not ours"


def test_env_agent_dir_replaces_gentle_shell_and_plain_pi_is_still_added(home, monkeypatch):
    custom = home / "custom-agent"
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(custom))
    (home / ".pi" / "agent").mkdir(parents=True)
    hooks.install_pi_hooks()
    assert installed(custom) and installed(home / ".pi" / "agent")
    assert not (home / ".gentle-shell").exists()


def test_env_agent_dir_pointing_at_plain_pi_installs_once(home, monkeypatch):
    plain = home / ".pi" / "agent"
    plain.mkdir(parents=True)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(plain))
    assert hooks.install_pi_hooks() is True
    assert installed(plain) and not (home / ".gentle-shell").exists()


def test_explicit_agent_dir_still_means_only_that_dir(home, tmp_path):
    (home / ".pi" / "agent").mkdir(parents=True)
    target = tmp_path / "elsewhere"
    hooks.install_pi_hooks(agent_dir=target)
    assert installed(target)
    assert not installed(home / ".pi" / "agent") and not installed(home / ".gentle-shell" / "agent")
