"""Hotbar (Tauri) process lifecycle, owned by the tray."""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

logger = logging.getLogger("clawd-tank.hotbar")

HOTBAR_EXE = "clawdy-hotbar.exe" if sys.platform == "win32" else "clawdy-hotbar"
PIDFILE = Path.home() / ".clawd-tank" / "hotbar.pid"
LOG_PATH = Path.home() / ".clawd-tank" / "hotbar.log"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def find_hotbar_exe(
    environ: Mapping[str, str] = os.environ,
    exe_dir: Optional[str] = None,
    repo_root: Path = _REPO_ROOT,
) -> Optional[str]:
    """CLAWDY_HOTBAR_EXE, then next to sys.executable, then a cargo release build
    (CARGO_TARGET_DIR, else the repo's own target dir)."""
    override = environ.get("CLAWDY_HOTBAR_EXE")
    if override and os.path.isabs(override) and os.path.isfile(override):
        return override
    if exe_dir is None:
        exe_dir = os.path.dirname(sys.executable)
    folders = [Path(exe_dir)]
    if environ.get("CARGO_TARGET_DIR"):
        folders.append(Path(environ["CARGO_TARGET_DIR"]) / "release")
    folders.append(repo_root / "hotbar" / "src-tauri" / "target" / "release")
    for folder in folders:
        candidate = folder / HOTBAR_EXE
        if candidate.is_file():
            return str(candidate)
    return None


def _image_path_of(pid: int) -> Optional[str]:
    """Full image path of a live process, or None (dead pid, access denied)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


_WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def webview2_version() -> Optional[str]:
    """Installed WebView2 Runtime version from the registry, or None when not found.

    The hotbar's windows need it; a fixed-version runtime shipped with another app is not
    registered here, so None means "not found", not "cannot work".
    """
    import winreg

    for hive, root in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
                       (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE"),
                       (winreg.HKEY_CURRENT_USER, "SOFTWARE")):
        try:
            with winreg.OpenKey(hive, root + "\\" + _WEBVIEW2_CLIENT) as key:
                version = winreg.QueryValueEx(key, "pv")[0]
        except OSError:
            continue
        if isinstance(version, str) and version not in ("", "0.0.0.0"):
            return version
    return None


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class HotbarProcess:
    def __init__(
        self,
        exe: Optional[str],
        *,
        popen: Callable = subprocess.Popen,
        run: Callable = subprocess.run,
        image_path_of: Callable[[int], Optional[str]] = _image_path_of,
        pidfile: Path = PIDFILE,
        log_path: Path = LOG_PATH,
        webview2_version: Callable[[], Optional[str]] = webview2_version,
    ):
        self._exe = exe
        self._popen = popen
        self._run = run
        self._image_path_of = image_path_of
        self._pidfile = pidfile
        self._log_path = log_path
        self._webview2_version = webview2_version
        self._process = None

    def _taskkill(self, pid: int) -> None:
        # No /T: the hotbar's WebView2 children exit with their host, and a
        # tree kill would also take programs the user started from run: cells.
        try:
            self._run(["taskkill", "/F", "/PID", str(pid)],
                      capture_output=True, text=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("taskkill failed for PID %d: %s", pid, e)

    def _kill_stale(self) -> None:
        """Kill an orphan from a crashed tray, only if the pid still runs our exe."""
        if sys.platform != "win32":
            return
        try:
            record = json.loads(self._pidfile.read_text(encoding="utf-8"))
            pid, recorded = record["pid"], record["exe"]
        except (OSError, ValueError, KeyError, TypeError):
            return
        if not isinstance(pid, int) or not isinstance(recorded, str):
            return
        image = self._image_path_of(pid)
        if image and _same_path(image, recorded) and _same_path(image, self._exe):
            logger.info("Killing stale hotbar (PID %d)", pid)
            self._taskkill(pid)

    def start(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True
        if not self._exe:
            logger.warning("Hotbar executable not found; skipping the hotbar")
            return False
        self._kill_stale()
        if sys.platform == "win32" and self._webview2_version() is None:
            logger.warning("WebView2 Runtime not found in the registry; the hotbar may exit at once "
                           "(install it from https://developer.microsoft.com/microsoft-edge/webview2/)")
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "ab") as log:
                self._process = self._popen(
                    [self._exe],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, "CLAWDY_PARENT_PID": str(os.getpid())},
                )
        except OSError as e:
            logger.warning("Could not start the hotbar: %s", e)
            self._process = None
            return False
        logger.info("Started hotbar (PID %d)", self._process.pid)
        return True

    def stop(self) -> None:
        """Synchronous and idempotent; safe from any thread."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        if sys.platform == "win32":
            self._taskkill(process.pid)
        else:
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass
        try:
            process.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            logger.warning("Hotbar still alive after kill (PID %d)", process.pid)
