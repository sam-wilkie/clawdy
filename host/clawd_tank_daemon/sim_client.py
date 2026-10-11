# host/clawd_tank_daemon/sim_client.py
"""TCP transport client for connecting to the Clawd Tank simulator."""

import asyncio
import json
import logging

logger = logging.getLogger("clawd-tank.sim")

SIM_DEFAULT_PORT = 19872
SIM_RETRY_INTERVAL = 5  # seconds


class SimClient:
    """TCP client that connects to the simulator's TCP listener."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = SIM_DEFAULT_PORT,
        on_disconnect_cb=None,
        on_connect_cb=None,
        on_event_cb=None,
        retry_interval: float = SIM_RETRY_INTERVAL,
        desktop_pet: bool = False,
    ):
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._on_disconnect_cb = on_disconnect_cb
        self._on_connect_cb = on_connect_cb
        self._on_event_cb = on_event_cb
        self._retry_interval = retry_interval
        # True when the other end is the Electron desktop pet rather than the
        # SDL2 simulator: the daemon sends it pet-only animations.
        self.desktop_pet = desktop_pet
        self._lock = asyncio.Lock()
        self._reader_task: asyncio.Task | None = None
        self._config_response: asyncio.Future | None = None

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Connect to the simulator. Retries until successful."""
        if self._writer is not None:
            await self.disconnect()
        while True:
            try:
                logger.info("Connecting to simulator at %s:%d...", self._host, self._port)
                self._reader, self._writer = await asyncio.open_connection(
                    self._host, self._port
                )
                logger.info("Connected to simulator")
                self._reader_task = asyncio.create_task(self._background_reader())
                if self._on_connect_cb:
                    self._on_connect_cb()
                return
            except (ConnectionRefusedError, OSError) as e:
                logger.debug("Simulator not available: %s, retrying...", e)
                await asyncio.sleep(self._retry_interval)

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = None
        self._reader = None

    async def ensure_connected(self) -> None:
        """Reconnect if disconnected."""
        if not self.is_connected:
            await self.connect()

    async def send_command(self, payload: dict) -> bool:
        """Send an arbitrary JSON command. Returns True on success."""
        return await self.write_notification(json.dumps(payload))

    async def write_notification(self, payload: str) -> bool:
        """Send a JSON payload followed by newline. Returns True on success."""
        async with self._lock:
            if not self.is_connected:
                logger.warning("Not connected to simulator, cannot write")
                return False
            try:
                self._writer.write((payload + "\n").encode("utf-8"))
                await self._writer.drain()
                return True
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.error("Simulator write failed: %s", e)
                self._handle_disconnect()
                return False

    async def read_config(self) -> dict:
        """Request and read config from simulator. Returns empty dict on error."""
        async with self._lock:
            if not self.is_connected:
                return {}
            try:
                self._config_response = asyncio.get_event_loop().create_future()
                self._writer.write(b'{"action":"read_config"}\n')
                await self._writer.drain()
                result = await asyncio.wait_for(self._config_response, timeout=2.0)
                return result
            except (asyncio.TimeoutError, asyncio.CancelledError, OSError) as e:
                logger.error("Config read failed: %s", e)
                self._handle_disconnect()
                return {}
            finally:
                self._config_response = None

    async def write_config(self, payload: str) -> bool:
        """Send a config write payload. Wraps in action envelope for TCP protocol."""
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return False
        data["action"] = "write_config"
        return await self.write_notification(json.dumps(data))

    async def _background_reader(self) -> None:
        """Read unsolicited messages from the simulator and dispatch them."""
        try:
            while self._reader and not self._reader.at_eof():
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    data = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                # A permission decision is an event, never a config reply: it
                # must reach the callback even while read_config is waiting.
                if isinstance(data, dict) and data.get("event") == "permission_decision":
                    self._dispatch_event(data)
                    continue
                # Config responses go to the waiting future
                if self._config_response and not self._config_response.done():
                    self._config_response.set_result(data)
                    continue
                # Events go to callback
                if isinstance(data, dict) and "event" in data:
                    self._dispatch_event(data)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        except asyncio.CancelledError:
            return
        self._handle_disconnect()

    def _dispatch_event(self, data: dict) -> None:
        """Deliver an inbound event; a failing callback must not end the reader."""
        if not self._on_event_cb:
            return
        try:
            self._on_event_cb(data)
        except Exception:
            logger.exception("Simulator event callback failed")

    def _handle_disconnect(self) -> None:
        """Clean up state and notify on disconnect."""
        self._writer = None
        self._reader = None
        if self._on_disconnect_cb:
            self._on_disconnect_cb()
