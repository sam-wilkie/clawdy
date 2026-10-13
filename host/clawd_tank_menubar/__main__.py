# host/clawd_tank_menubar/__main__.py
"""Entry point: `python -m clawd_tank_menubar`.

Dispatches to the macOS rumps app (unchanged) or the Windows pystray tray.
Runnable in a dev checkout on either platform without a packaged build —
app.py (which imports rumps) is only imported on darwin, so this module
itself has no import-time platform dependency.
"""
import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".clawd-tank" / "logs"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Run by the Windows uninstaller before it deletes the notify exe, so Claude
# Code is not left invoking a program that no longer exists on every hook.
UNINSTALL_HOOKS_FLAG = "--uninstall-hooks"
INSTALL_CODEX_HOOKS_FLAG = "--install-codex-hooks"
INSTALL_KIRO_HOOKS_FLAG = "--install-kiro-hooks"


def _uninstall_hooks() -> int:
    """Remove our Claude Code, Codex, tracked Kiro, and Antigravity hooks.

    Starts neither the tray nor the daemon. Logs to the usual log file, through
    a handler removed again before returning, since a packaged windowed build
    has no console to report to.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_DIR / "clawd-tank.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    app_logger = logging.getLogger("clawd-tank")
    previous_level = app_logger.level
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    logger = logging.getLogger("clawd-tank.menubar")
    try:
        from . import hooks
        try:
            removed_claude = hooks.uninstall_hooks()
            removed_codex = hooks.uninstall_codex_hooks()
            removed_kiro = hooks.uninstall_tracked_kiro_hooks()
            removed_antigravity = hooks.uninstall_antigravity_hooks()
            removed_opencode = hooks.uninstall_opencode_hooks()
            removed = (removed_claude and removed_codex and removed_kiro
                       and removed_antigravity and removed_opencode)
        except Exception:
            logger.exception("Uninstalling agent hooks failed")
            return 1
        if removed:
            logger.info(
                "Uninstalled Claude Code, Codex, tracked Kiro, and Antigravity hooks"
            )
            return 0
        logger.error("One or more agent hooks were not uninstalled")
        return 1
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(previous_level)
        handler.close()


def _install_optional_hooks(args: list[str]) -> int | None:
    """Installer-only entry point for Codex or one selected Kiro workspace."""
    try:
        from . import hooks
        if args == [INSTALL_CODEX_HOOKS_FLAG]:
            return 0 if hooks.install_codex_hooks() else 1
        if len(args) == 2 and args[0] == INSTALL_KIRO_HOOKS_FLAG:
            hooks.install_notify_script()
            return 0 if hooks.install_kiro_hooks(Path(args[1])) else 1
    except Exception:
        return 1
    return None


def _run_macos() -> None:
    from .app import main
    main()


def _run_windows() -> None:
    import traceback

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "clawd-tank.log"

    # A packaged (PyInstaller, console=False) build has no console, and
    # sys.stdout/sys.stderr are not readable/writable streams in that mode
    # (bootloader-dependent: None on some versions, a stub that raises on
    # others). A bare logging.StreamHandler() defaulting to sys.stderr can
    # therefore fail before the FileHandler ever gets its first record —
    # this was caught by the packaging step's manual run: the built exe
    # produced a completely empty log file with console=False, discovered
    # only by rebuilding with console=True to see the traceback. Only add
    # the console handler when there's an actual usable stream; always keep
    # the file handler so a packaged run never fails silently.
    handlers = [logging.FileHandler(log_file)]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=handlers,
    )
    logger = logging.getLogger("clawd-tank.menubar")

    try:
        from . import hooks
        from .controller import ClawdTankController
        from .version import get_version
        from .windows_tray import WindowsTrayView

        logger.info("Clawd Tank %s starting (Windows tray)", get_version())

        hooks.install_notify_script()

        hooks.install_statusline_bridge_script()
        if not hooks.are_hooks_installed():
            logger.info("Hooks outdated, auto-updating...")
            hooks.install_hooks()

        from clawd_tank_daemon.sim_process import SimProcessManager
        SimProcessManager.kill_stale_sims()

        view = WindowsTrayView()
        controller = ClawdTankController(view)
        view.build(controller)
        controller.start()
        view.run()
    except Exception:
        # Same silent-crash risk as the logging handler above: a packaged
        # windowed build has nowhere else to surface this. Log it, in
        # whatever handlers actually work, then re-raise.
        logger.critical("Unhandled exception, exiting:\n%s", traceback.format_exc())
        raise


def main() -> None:
    if UNINSTALL_HOOKS_FLAG in sys.argv[1:]:
        sys.exit(_uninstall_hooks())
    setup_result = _install_optional_hooks(sys.argv[1:])
    if setup_result is not None:
        sys.exit(setup_result)
    if sys.platform == "darwin":
        _run_macos()
    else:
        _run_windows()


if __name__ == "__main__":
    main()
