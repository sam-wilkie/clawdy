"""Watch Kiro's own log files for the events its hooks never report.

Kiro (IDE and CLI) fires its SessionStart hook only together with the first
prompt, so an opened-but-unused Kiro CLI shows no crab, and hitting the usage
limit fires no hook at all, so the crab is stuck "thinking". Kiro does write
both facts to its log: every Kiro process appends JSON Lines to
``~/.kiro/logs/<YYYYMMDDTHHMMSSmmm>/kiro.log``. This module tails those files
and turns the two relevant lines into the daemon's normalized messages:

  * ``session.new.total {"sessionId": ..., "outcome": "resolved"}`` ->
    ``session_start`` (the crab appears when Kiro opens)
  * ``UsageLimitReachedError: ...`` (``conversationId`` is the session) ->
    an exhausted ``StopFailure`` add, the same shape Claude Code's out-of-credits
    StopFailure produces (``protocol.hook_payload_to_daemon_message``)

Session ids get the same ``kiro:`` prefix the hook path uses, so later hook
events land on the same daemon session. Messages carry ``"from_log": True`` so
the daemon can tell them apart from hook events.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .kiro_protocol import KIRO_DISPLAY_NAME, KIRO_SESSION_PREFIX

logger = logging.getLogger("clawd-tank")

KIRO_LOG_NAME = "kiro.log"
SESSION_NEW_PREFIX = "session.new.total "
USAGE_LIMIT_PREFIX = "UsageLimitReachedError"
USAGE_LIMIT_MESSAGE = "Usage limit reached"

# Only logs written to recently are followed, and at most this many of them
# (an IDE and a CLI or two are live at once; old folders are dead processes).
RECENT_LOG_MAX_AGE_SECS = 24 * 3600
MAX_FOLLOWED_LOGS = 8


def default_kiro_logs_dir() -> Path:
    return Path.home() / ".kiro" / "logs"


def parse_kiro_log_line(line: str) -> Optional[dict]:
    """Daemon message for one Kiro log line, or None if the line is irrelevant."""
    try:
        entry = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(entry, dict):
        return None
    message = entry.get("message")
    if not isinstance(message, str):
        return None

    if message.startswith(SESSION_NEW_PREFIX):
        try:
            detail = json.loads(message[len(SESSION_NEW_PREFIX):])
        except ValueError:
            return None
        if not isinstance(detail, dict):
            return None
        session_id = detail.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            return None
        if detail.get("outcome", "resolved") != "resolved":
            return None
        return {
            "event": "session_start",
            "session_id": KIRO_SESSION_PREFIX + session_id,
            "project": KIRO_DISPLAY_NAME,
            "pid": None,
            "from_log": True,
        }

    # The title model logs its own UsageLimitReachedError as a warn line whose
    # message starts with "llm.invokeTitleModel.error"; only the turn's error
    # line starts with the error name itself.
    if message.startswith(USAGE_LIMIT_PREFIX):
        session_id = entry.get("conversationId")
        if not isinstance(session_id, str) or not session_id:
            return None
        return {
            "event": "add",
            "hook": "StopFailure",
            "session_id": KIRO_SESSION_PREFIX + session_id,
            "project": KIRO_DISPLAY_NAME,
            "message": USAGE_LIMIT_MESSAGE,
            "pid": None,
            "exhausted": True,
            "from_log": True,
        }
    return None


class KiroLogTailer:
    """Follows the recent ``kiro.log`` files under a Kiro logs directory.

    Files that already exist on the first poll start at end-of-file (history is
    not replayed); files that appear later are read from the start. Only whole
    lines are consumed, and a file that shrank is re-read from the start.
    """

    def __init__(self, base_dir: Path):
        self._base_dir = Path(base_dir)
        self._offsets: dict[Path, int] = {}
        self._primed = False

    def _all_logs(self) -> list[Path]:
        if not self._base_dir.is_dir():
            return []
        return [p for p in self._base_dir.glob("*/" + KIRO_LOG_NAME) if p.is_file()]

    def poll(self) -> list[dict]:
        logs = self._all_logs()
        if not self._primed:
            # Baseline every existing log at its current size, recent or not, so
            # an old log that wakes up later is not replayed from the start.
            self._primed = True
            for path in logs:
                try:
                    self._offsets[path] = path.stat().st_size
                except OSError:
                    pass
            return []

        now = time.time()
        recent = []
        for path in logs:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if now - mtime <= RECENT_LOG_MAX_AGE_SECS:
                recent.append((mtime, path))
        recent.sort(reverse=True)

        messages = []
        for _, path in recent[:MAX_FOLLOWED_LOGS]:
            messages.extend(self._read_new_lines(path))
        live = set(logs)
        for path in [p for p in self._offsets if p not in live]:
            del self._offsets[path]
        return messages

    def _read_new_lines(self, path: Path) -> list[dict]:
        offset = self._offsets.get(path, 0)
        try:
            with open(path, "rb") as f:
                size = f.seek(0, 2)
                if size < offset:
                    offset = 0  # truncated or replaced
                f.seek(offset)
                data = f.read(size - offset)
        except OSError as e:
            logger.debug("Kiro log read failed for %s: %s", path, e)
            return []
        end = data.rfind(b"\n")
        if end < 0:
            self._offsets[path] = offset
            return []
        self._offsets[path] = offset + end + 1
        messages = []
        for line in data[:end].decode("utf-8", errors="replace").splitlines():
            msg = parse_kiro_log_line(line.strip())
            if msg is not None:
                messages.append(msg)
        return messages


async def run_kiro_log_watcher(
    handler: Callable[[dict], Awaitable[None]],
    base_dir: Optional[Path] = None,
    interval: float = 1.0,
) -> None:
    """Poll Kiro's logs forever, feeding each parsed message to `handler`.

    Never raises (except on cancellation): a failing poll or handler is logged
    and the loop keeps going."""
    tailer = KiroLogTailer(base_dir if base_dir is not None else default_kiro_logs_dir())
    while True:
        try:
            messages = tailer.poll()
        except Exception:
            logger.warning("Kiro log poll failed", exc_info=True)
            messages = []
        for msg in messages:
            try:
                await handler(msg)
            except Exception:
                logger.warning("Kiro log message handling failed", exc_info=True)
        await asyncio.sleep(interval)
