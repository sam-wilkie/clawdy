"""T5b: the tray toggle installs and removes the Pi extension (S4, S1)."""

from clawd_tank_menubar import hooks
from clawd_tank_menubar.controller import ClawdTankController


class FakeView:
    def __init__(self):
        self.renders = []
        self.alerts = []

    def render(self, state):
        self.renders.append(state)

    def alert(self, title, message):
        self.alerts.append((title, message))

    def quit(self):
        pass

    def choose_folder(self, title):
        return None


def _controller(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "agent"))
    view = FakeView()
    controller = ClawdTankController(
        view,
        prefs_path=tmp_path / "prefs.json",
        sim_process_factory=lambda **kw: None,
    )
    return controller, view


def test_toggle_installs_then_removes_the_pi_extension(tmp_path, monkeypatch):
    controller, view = _controller(tmp_path, monkeypatch)
    ext = tmp_path / "agent" / "extensions" / "clawd-tank.js"
    controller.toggle_pi_hooks()
    assert ext.is_file()
    assert view.alerts[-1][0] == "Pi Extension Installed"
    controller.toggle_pi_hooks()
    assert not ext.exists()
    assert view.alerts[-1][0] == "Pi Extension Removed"


def test_pi_state_is_exposed_to_the_views(tmp_path, monkeypatch):
    controller, _ = _controller(tmp_path, monkeypatch)
    assert controller.pi_hooks_installed is False
    controller.toggle_pi_hooks()
    assert controller.pi_hooks_installed is True
