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

        Looked up in CLAWDY_DESKTOP_DIR, else the copy bundled with the app
        (Contents/Resources/desktop on macOS, desktop/ next to the exe on the
        frozen Windows build), else the repo's desktop/ folder. Needs its
        dependencies installed (pnpm install), which leaves the Electron binary
        name in node_modules/electron/path.txt. CLAWDY_DESKTOP_PET=0 forces the
        SDL2 window.
        """
        if os.environ.get("CLAWDY_DESKTOP_PET") == "0":
            return None
        app_dir = os.environ.get("CLAWDY_DESKTOP_DIR")
        if not app_dir and sys.platform == "darwin":
            # The release bundles the Electron runtime and pet sources under
            # Contents/Resources/desktop. Resolve it from the host app so the
            # installed menu-bar app can launch the pet without a repo checkout.
            try:
                from Foundation import NSBundle
                bundle = NSBundle.mainBundle()
                if bundle:
                    candidate = os.path.join(
                        bundle.bundlePath(), "Contents", "Resources", "desktop"
                    )
                    if os.path.isfile(os.path.join(candidate, "main.js")):
                        app_dir = candidate
            except ImportError:
                pass
        if not app_dir and getattr(sys, "frozen", False):
            # The Windows release is a flat PyInstaller onedir, so the pet ships
            # next to MargaritaTank.exe — the same place _find_binary() looks for
            # the simulator. Not gated on the platform: a frozen flat layout has
            # no .app bundle anywhere, and the isfile check below rejects any
            # build that did not ship the pet. getattr, not sys.frozen, because
            # tests fake the sys module.
            candidate = os.path.join(os.path.dirname(sys.executable), "desktop")
            if os.path.isfile(os.path.join(candidate, "main.js")):
                app_dir = candidate
        if not app_dir:
            app_dir = os.path.join(
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
            env = {**os.environ, "CLAWDY_PORT": str(self._port),
                   "CLAWDY_PARENT_PID": str(os.getpid())}
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
        self._client = SimClient(
            port=self._port, on_event_cb=self._handle_sim_event, desktop_pet=bool(pet)
        )
        return self._client

    async def stop(self) -> None:
        # Send a graceful quit command to the Electron pet / simulator so it
        # can close its windows and exit on its own before we force-kill it.
        if self._client and self._client.is_connected:
            try:
                await self._client.send_command({"action": "quit"})
            except Exception:
                pass  # best effort; force-kill below is the safety net
        if self._client:
            await self._client.disconnect()
            self._client = None
        if self._process and self._process.returncode is None:
            logger.info("Stopping simulator process (PID %d)", self._process.pid)
            try:
                # Give the process up to 2 s to exit after the quit command.
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                # Still alive — force-kill the whole tree.
                logger.warning("Simulator did not exit after quit, force-killing")
                self._kill_process_tree()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("Simulator still alive after tree kill")
            self._process = None

    def _kill_process_tree(self) -> None:
        """Synchronously kill the process we spawned (and, on Windows, its tree).

        Electron starts GPU/renderer children, and TerminateProcess on the main
        exe alone leaves them behind. The tree is addressed by the PID of the
        process we started, never by image name: other Electron apps (editors,
        IDEs) run on the same machine and must not be touched. Off Windows the
        plain kill is used. Safe to call repeatedly and from any thread.
        """
        process = self._process
        if process is None or process.returncode is not None:
            return
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True, text=True, timeout=5,
                )
                return
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
                logger.warning("taskkill failed for PID %d: %s", process.pid, e)
        try:
            process.kill()
        except (ProcessLookupError, OSError):
            pass  # already gone

    def kill_sync(self) -> None:
        """Kill without needing the event loop: the quit path calls this when
        the daemon loop has already stopped or the async shutdown timed out."""
        self._kill_process_tree()

    async def kill(self) -> None:
        """Immediately kill the simulator process without graceful shutdown."""
        if self._process and self._process.returncode is None:
            self._kill_process_tree()
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
