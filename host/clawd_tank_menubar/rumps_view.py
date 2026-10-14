# host/clawd_tank_menubar/rumps_view.py
"""The macOS TrayView implementation: rumps menu construction and repainting.

Moved out of app.py verbatim wherever possible. app.py itself now only owns
the rumps.App subclass shell (rumps requires @rumps.timer-decorated methods
to live on the App instance itself) and wires its callbacks to the
controller; every menu-building, repainting, alert, and quit call lives here.
"""
import logging
from typing import Optional

import rumps

from .controller import ClawdTankController, SESSION_TIMEOUT_OPTIONS, TrayState
from .slider import create_slider_menu_item

logger = logging.getLogger("clawd-tank.menubar")

def _bring_to_front() -> None:
    """Activate the app so its next modal alert shows above other windows.

    A menu-bar-only app (LSUIElement) is never the active app, so without this
    rumps.alert opens behind whatever window has focus."""
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        logger.debug("Could not activate the app before an alert", exc_info=True)


_ICON_FILES = {
    "disconnected": "crab-disconnected",
    "connected": "crab-connected",
    "notifications": "crab-notifications",
}


class RumpsTrayView:
    """Builds and repaints the rumps menu. Constructed in two steps because
    the controller needs a view to be constructed itself, and this view's
    initial widget state is read from the controller: `RumpsTrayView(app)`
    just remembers the rumps.App to draw into, then `build(controller)`
    constructs the menu once the controller (and its preferences-derived
    initial state) exists.
    """

    def __init__(self, app: rumps.App):
        self._app = app

    def build(self, controller: ClawdTankController) -> None:
        # --- BLE submenu ---
        self._ble_menu = rumps.MenuItem("BLE — Disabled")
        self._ble_status = rumps.MenuItem("Status: Initializing...")
        self._ble_status.set_callback(None)
        self._ble_enabled_toggle = rumps.MenuItem(
            "Enabled", callback=lambda _sender: controller.toggle_ble_enabled()
        )
        self._ble_enabled_toggle.state = controller.ble_enabled
        self._ble_reconnect = rumps.MenuItem(
            "Reconnect", callback=None
        )
        self._on_reconnect = lambda _sender: controller.reconnect()
        self._ble_menu.update([
            self._ble_status,
            None,
            self._ble_enabled_toggle,
            None,
            self._ble_reconnect,
        ])

        # --- Simulator submenu ---
        self._sim_menu = rumps.MenuItem("Simulator — Disabled")
        self._sim_status = rumps.MenuItem("Status: Initializing...")
        self._sim_status.set_callback(None)
        self._sim_enabled_toggle = rumps.MenuItem(
            "Enabled", callback=lambda _sender: controller.toggle_sim_enabled()
        )
        self._sim_enabled_toggle.state = controller.sim_enabled
        self._sim_window_toggle = rumps.MenuItem("Show Window", callback=None)
        self._sim_window_toggle.state = controller.sim_window_visible
        self._sim_pinned_toggle = rumps.MenuItem("Always on Top", callback=None)
        self._sim_pinned_toggle.state = controller.sim_pinned
        self._on_toggle_sim_window = lambda _sender: controller.toggle_sim_window()
        self._on_toggle_sim_pinned = lambda _sender: controller.toggle_sim_pinned()
        self._sim_menu.update([
            self._sim_status,
            None,
            self._sim_enabled_toggle,
            None,
            self._sim_window_toggle,
            self._sim_pinned_toggle,
        ])

        # Floating Electron desktop pet (falls back to SDL2 in dev if Electron
        # dependencies are missing).
        self._sim_desk_item = rumps.MenuItem(
            "Electron Desktop Pet",
            callback=lambda _sender: controller.toggle_sim_desk(),
        )
        self._sim_desk_item.state = controller.sim_desk

        # Brightness slider - rumps MenuItem with custom NSView
        self._brightness_slider = create_slider_menu_item(
            "Brightness", min_val=0, max_val=255, initial=102,
            on_change=lambda value: controller.set_brightness(value),
        )
        self._brightness_item = rumps.MenuItem("Brightness")
        self._brightness_item._menuitem.setView_(self._brightness_slider.view)

        # Session timeout submenu
        self._session_timeout_menu = rumps.MenuItem("Session Timeout")
        self._session_timeout_items: dict[int, rumps.MenuItem] = {}
        for label, seconds in SESSION_TIMEOUT_OPTIONS:
            item = rumps.MenuItem(
                label,
                callback=lambda _sender, secs=seconds: controller.select_session_timeout(secs),
            )
            item.state = (seconds == controller.session_timeout_seconds)
            self._session_timeout_menu.add(item)
            self._session_timeout_items[seconds] = item

        # Claude Code hooks
        self._hooks_item = rumps.MenuItem(
            "Install Claude Code Hooks",
            callback=lambda _sender: controller.install_hooks(),
        )
        self._hooks_item.state = controller.hooks_installed

        # Kiro hooks: per-workspace, so this is an action (pick a folder), not a
        # global toggle like the Claude hooks above.
        self._kiro_hooks_item = rumps.MenuItem(
            "Install Kiro Hooks (choose folder)...",
            callback=lambda _sender: controller.install_kiro_hooks(),
        )

        # PR1: OpenCode hooks — stateless enable/disable like Claude. The check
        # reflects hooks.are_opencode_hooks_installed() (queried on every render),
        # not an internal flag, so disk edits show up without an app restart.
        self._opencode_hooks_item = rumps.MenuItem(
            "Install OpenCode Hooks",
            callback=lambda _sender: controller.toggle_opencode_hooks(),
        )
        self._opencode_hooks_item.state = controller.opencode_hooks_installed

        # Antigravity (agy CLI + IDE) plugin: same enable/disable pattern.
        self._antigravity_hooks_item = rumps.MenuItem(
            "Install Antigravity Hooks",
            callback=lambda _sender: controller.toggle_antigravity_hooks(),
        )
        self._antigravity_hooks_item.state = controller.antigravity_hooks_installed

        # Pi (gentle-shell) extension: same stateless enable/disable pattern.
        self._pi_hooks_item = rumps.MenuItem(
            "Install Pi Extension",
            callback=lambda _sender: controller.toggle_pi_hooks(),
        )
        self._pi_hooks_item.state = controller.pi_hooks_installed

        # Launch at login
        self._login_item = rumps.MenuItem(
            "Launch at Login",
            callback=lambda _sender: controller.toggle_login(),
        )
        self._login_item.state = controller.login_enabled

        # Version
        from .version import get_version
        self._version_item = rumps.MenuItem(f"Version: {get_version()}")
        self._version_item.set_callback(None)

        # Quit
        self._quit_item = rumps.MenuItem(
            "Quit Clawdy", callback=lambda _sender: controller.quit()
        )

        # Assemble menu
        self._app.menu = [
            self._ble_menu,
            self._sim_menu,
            self._sim_desk_item,
            None,
            self._brightness_item,
            self._session_timeout_menu,
            None,
            self._hooks_item,
            self._kiro_hooks_item,
            self._opencode_hooks_item,
            self._antigravity_hooks_item,
            self._pi_hooks_item,
            self._login_item,
            None,
            self._version_item,
            self._quit_item,
        ]

        # Set initial icon and hide text title so only the icon shows in the menu bar
        self._app.icon = self._icon_path("crab-disconnected")
        self._app.template = True
        self._app.title = ""

    # --- TrayView protocol -------------------------------------------------

    def render(self, state: TrayState) -> None:
        """Repaint the whole menu from one snapshot, marshaled onto the main
        thread — the same PyObjC hop app.py used to do in
        _schedule_menu_update(), just applied uniformly (some triggers, e.g.
        toggle clicks, were already on the main thread and repainted
        in-place; marshaling those too is a no-op delay of a few ms, and
        removes any risk of a future caller forgetting to marshal)."""
        try:
            from PyObjCTools.AppHelper import callAfter
            callAfter(self._paint, state)
        except ImportError:
            self._paint(state)

    def _paint(self, state: TrayState) -> None:
        """Must run on the main thread. Equivalent to the original
        _update_menu_state(), reading from `state` instead of instance
        attributes that used to double as the state itself."""
        # --- BLE submenu state ---
        if not state.ble_enabled:
            self._ble_menu.title = "BLE — Disabled"
            self._ble_status.title = "Status: Disabled"
            self._ble_reconnect.set_callback(None)
        else:
            if state.ble_connected:
                self._ble_menu.title = "BLE \U0001F7E2 Connected"
                self._ble_status.title = "Status: Connected"
            else:
                self._ble_menu.title = "BLE \U0001F7E1 Connecting..."
                self._ble_status.title = "Status: Connecting..."
            self._ble_reconnect.set_callback(self._on_reconnect)
        self._ble_enabled_toggle.state = state.ble_enabled

        # --- Simulator submenu state ---
        if not state.sim_enabled:
            self._sim_menu.title = "Simulator — Disabled"
            self._sim_status.title = "Status: Disabled"
            self._sim_window_toggle.set_callback(None)
            self._sim_pinned_toggle.set_callback(None)
        else:
            if state.sim_connected:
                self._sim_menu.title = "Simulator \U0001F7E2 Running"
                self._sim_status.title = "Status: Running"
            else:
                self._sim_menu.title = "Simulator \U0001F7E1 Connecting..."
                self._sim_status.title = "Status: Connecting..."
            if state.sim_desk:  # the desk window is always shown and on top
                self._sim_menu.title = "Simulator \U0001F7E2 Floating desk pet"
                self._sim_status.title = "Status: Floating desk pet"
                self._sim_window_toggle.set_callback(None)
                self._sim_pinned_toggle.set_callback(None)
            else:
                self._sim_window_toggle.set_callback(self._on_toggle_sim_window)
                self._sim_pinned_toggle.set_callback(self._on_toggle_sim_pinned)
        self._sim_desk_item.state = state.sim_desk
        self._sim_enabled_toggle.state = state.sim_enabled
        self._sim_window_toggle.state = state.sim_window_visible
        self._sim_pinned_toggle.state = state.sim_pinned

        # --- Brightness ---
        # set_value() then set_enabled() — in that order — so a disabled
        # slider always ends up showing "--" (set_enabled(False) overwrites
        # the label), matching the original which simply never called
        # set_value() while disconnected.
        self._brightness_slider.set_value(state.brightness)
        self._brightness_slider.set_enabled(state.brightness_enabled)

        # --- Session timeout ---
        for seconds, item in self._session_timeout_items.items():
            item.state = (seconds == state.session_timeout_seconds)

        # --- Hooks / login ---
        self._hooks_item.state = state.hooks_installed
        self._opencode_hooks_item.state = state.opencode_hooks_installed
        self._opencode_hooks_item.title = "Uninstall OpenCode Hooks" if state.opencode_hooks_installed else "Install OpenCode Hooks"
        self._antigravity_hooks_item.state = state.antigravity_hooks_installed
        self._pi_hooks_item.state = state.pi_hooks_installed
        self._login_item.state = state.login_enabled

        # --- Icon and global state ---
        self._app.icon = self._icon_path(_ICON_FILES[state.icon])
        self._app.title = ""

    def alert(self, title: str, message: str) -> None:
        _bring_to_front()
        rumps.alert(title=title, message=message)

    def choose_folder(self, title: str) -> Optional[str]:
        """Native macOS folder picker (NSOpenPanel). Returns the chosen path, or
        None if the user cancels or AppKit is unavailable."""
        _bring_to_front()
        try:
            from AppKit import NSOpenPanel
        except Exception:
            logger.warning("AppKit unavailable; cannot show the folder picker")
            return None
        try:
            panel = NSOpenPanel.openPanel()
            panel.setCanChooseDirectories_(True)
            panel.setCanChooseFiles_(False)
            panel.setAllowsMultipleSelection_(False)
            panel.setMessage_(title)
            # NSModalResponseOK == 1
            if panel.runModal() != 1:
                return None
            urls = panel.URLs()
            if not urls or urls.count() == 0:
                return None
            return urls.objectAtIndex_(0).path()
        except Exception:
            logger.exception("Folder picker failed")
            return None

    def quit(self) -> None:
        rumps.quit_application()

    # --- Helpers -------------------------------------------------------

    def _icon_path(self, name: str) -> Optional[str]:
        """Return path to icon file, or None if not found."""
        import importlib.resources
        try:
            icons_dir = importlib.resources.files("clawd_tank_menubar") / "icons"
            path = icons_dir / f"{name}.png"
            if hasattr(path, "__fspath__"):
                return str(path)
        except Exception:
            pass
        return None
