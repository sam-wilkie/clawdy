"""Simulator process lifecycle manager."""
import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
from typing import Callable, Optional

from .sim_client import SimClient, SIM_DEFAULT_PORT

logger = logging.getLogger("clawd-tank.sim-process")

SIM_BINARY = "clawd-tank-sim.exe" if sys.platform == "win32" else "clawd-tank-sim"


class SimProcessManager:
    def __init__(self, port: int = SIM_DEFAULT_PORT, on_window_event: Optional[Callable] = None,
                 start_pinned: bool = False, desk: bool = False):
        self._port = port
        self._process: Optional[asyncio.subprocess.Process] = None
        self._client: Optional[SimClient] = None
        self._on_window_event = on_window_event
        self._start_pinned = start_pinned
        self._desk = desk

    def _find_binary(self) -> Optional[str]:
        # 1. Contents/Resources/ (inside .app bundle — helper binaries belong here,
        #    not in Contents/MacOS/, to avoid macOS treating them as the main app)
        #    There is no .app bundle off macOS, and Foundation only exists there.
        if sys.platform == "darwin":
            try:
                from Foundation import NSBundle
                bundle = NSBundle.mainBundle()
                if bundle:
                    candidate = os.path.join(bundle.bundlePath(), "Contents", "Resources", "clawd-tank-sim")
                    if os.path.isfile(candidate):
                        return candidate
            except ImportError:
                pass
        # 2. Next to sys.executable (fallback for non-bundle environments)
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, SIM_BINARY)
        if os.path.isfile(candidate):
            return candidate
        # 3. PATH lookup (development) — which() applies PATHEXT on Windows,
        #    so the bare name still resolves the .exe there.
        return shutil.which("clawd-tank-sim")

    def _find_desktop_pet(self) -> Optional[list]:
        """Return [electron_exe, app_dir] for the Electron desktop pet, or None.

        Looked up in CLAWDY_DESKTOP_DIR, else the repo's desktop/ folder (a source
        checkout; frozen builds do not ship it). Needs its dependencies installed
        (pnpm install), which leaves the Electron binary name in
        node_modules/electron/path.txt. CLAWDY_DESKTOP_PET=0 forces the SDL2 window.
        """
        if os.environ.get("CLAWDY_DESKTOP_PET") == "0":
            return None
        app_dir = os.environ.get("CLAWDY_DESKTOP_DIR") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "desktop",
        )
        electron_dir = os.path.join(app_dir, "node_modules", "electron")
        try:
            with open(os.path.join(electron_dir, "path.txt"), encoding="utf-8") as fh:
                exe = os.path.join(electron_dir, "dist", fh.read().strip())
        except OSError:
            return None
        if not os.path.isfile(exe) or not os.path.isfile(os.path.join(app_dir, "main.js")):
            return None
        return [exe, app_dir]

    async def _is_port_in_use(self) -> bool:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", self._port), timeout=1.0)
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            return False

    def _handle_sim_event(self, event: dict) -> None:
        if self._on_window_event:
            self._on_window_event(event)

    @staticmethod
    def kill_stale_sims() -> None:
        """Kill ALL clawd-tank-sim processes. Safe at startup since any existing
        sim is necessarily orphaned from a previous app instance.
        Synchronous — call before the asyncio loop starts."""
        if sys.platform == "win32":
            # No pkill, and no stock way to match on the command line either;
            # taskkill matches the image name, which is enough because the name
            # is ours. /T takes any child it spawned with it.
            command = ["taskkill", "/F", "/T", "/IM", SIM_BINARY]
        else:
            command = ["pkill", "-9", "-f", "clawd-tank-sim"]
        try:
            result = subprocess.run(
                command,
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info("Killed stale clawd-tank-sim processes")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("Failed to kill stale sims: %s", e)

    async def _log_stream(self, stream, level) -> None:
        if not stream:
            return
        try:
            async for line in stream:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.log(level, "%s", text)
        except (ValueError, asyncio.CancelledError):
            pass

    async def start(self) -> Optional[SimClient]:
        # Wait for port to be released (stale sims killed in main() before event loop)
        if await self._is_port_in_use():
            logger.warning("Port %d in use, waiting for release after stale sim kill", self._port)
            for _ in range(10):
                await asyncio.sleep(0.5)
                if not await self._is_port_in_use():
                    break
            else:
                logger.error("Port %d still in use after waiting", self._port)
                return None

        binary = self._find_binary()
        pet = self._find_desktop_pet() if self._desk else None
        env = None
        if pet:
            # Desk mode with the Electron pet (desktop/): it speaks the same TCP
            # protocol as the simulator, so the SimClient below drives it unchanged.
            args = list(pet)
            env = {**os.environ, "CLAWDY_PORT": str(self._port)}
        elif not binary:
            logger.error("clawd-tank-sim binary not found")
            return None
        elif self._desk:
            # Desk pet: a visible, transparent, always-on-top crab-only window
            # (the simulator defaults --desk to scale 2 and pins it itself).
            args = [binary, "--listen", str(self._port), "--desk"]
        else:
            args = [binary, "--listen", str(self._port), "--hidden"]
            if self._start_pinned:
                args.append("--pinned")
        logger.info("Starting %s: %s", "desktop pet" if pet else "simulator", " ".join(args))
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        asyncio.create_task(self._log_stream(self._process.stdout, logging.INFO))
        asyncio.create_task(self._log_stream(self._process.stderr, logging.WARNING))
        await asyncio.sleep(0.3)
        self._client = SimClient(port=self._port, on_event_cb=self._handle_sim_event)
        return self._client

    async def stop(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
        if self._process and self._process.returncode is None:
            logger.info("Stopping simulator process (PID %d)", self._process.pid)
            if sys.platform == "win32":
                # Windows has no SIGTERM: send_signal(SIGTERM) is literally
                # TerminateProcess, so this is a kill however it is spelled and
                # the simulator gets no chance to tidy up. Saying terminate()
                # keeps the code honest about that. The TCP link is already
                # closed above, which is the only shutdown notice it does get.
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("Simulator did not exit, sending SIGKILL")
                self._process.kill()
                await self._process.wait()
            self._process = None

    async def kill(self) -> None:
        """Immediately kill the simulator process without graceful shutdown."""
        if self._process and self._process.returncode is None:
            self._process.kill()
            await self._process.wait()
            self._process = None

    async def show_window(self) -> bool:
        if self._client and self._client.is_connected:
            return await self._client.send_command({"action": "show_window"})
        return False

    async def hide_window(self) -> bool:
        if self._client and self._client.is_connected:
            return await self._client.send_command({"action": "hide_window"})
        return False

    async def set_pinned(self, pinned: bool) -> bool:
        if self._client and self._client.is_connected:
            return await self._client.send_command({"action": "set_window", "pinned": pinned})
        return False

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None
