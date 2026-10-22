"""Read-only Codex usage and estimated API cost; run refresh via asyncio.to_thread."""

import json
import logging
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Optional

from .usage_common import JsonlTailReader, Prices, project_key

logger = logging.getLogger(__name__)

# USD per million: input, output, cache write, unused 1h tier, cache read.
# Standard short-context API equivalents; long-context/service-tier uplifts are
# not modeled. Unverified models deliberately remain unpriced.
CODEX_PRICES: Prices = {
    # Verified 2026-10-16: https://developers.openai.com/api/docs/pricing
    "gpt-6.1-sol": (2, 10, 2.5, 0, 0.10),
}


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class CodexUsageReader(JsonlTailReader):
    cost_kind = "estimated"

    def __init__(
        self,
        root: Path,
        tz: Optional[tzinfo] = None,
        retention_days: int = 62,
        temp_root: Optional[str] = None,
    ):
        super().__init__(root, tz, retention_days, temp_root, CODEX_PRICES)
        self._retention_days = retention_days
        self.status = "absent"

    def refresh(self) -> None:
        self.status = "ok" if self._root.is_dir() else "absent"
        if self.status == "absent":
            super().__init__(self._root, self._tz, self._retention_days,
                             self._temp_root, CODEX_PRICES)
            return
        super().refresh()

    def _ingest(self, raw: bytes, ctx: dict) -> None:
        try:
            obj = json.loads(raw)
            kind, payload = obj.get("type"), obj.get("payload", {})
            if kind == "session_meta":
                if "key" not in ctx:
                    cwd = payload.get("cwd")
                    ctx["key"] = project_key(cwd, self._temp_root) if isinstance(cwd, str) else None
                return
            if kind == "turn_context" or (kind == "event_msg" and
                                         payload.get("type") == "thread_settings_applied"):
                model = payload.get("model")
                if isinstance(model, str):
                    ctx["model"] = model
                return
            if kind != "token_usage_record":
                return  # token_count is cumulative and must never contribute.
            key = ctx.get("key")
            if key is None:
                if "key" not in ctx:
                    logger.warning("codex usage: skipping response without session metadata")
                return
            usage, rid = payload["usage"], payload["response_id"]
            if not isinstance(usage, dict) or not isinstance(rid, str) or not rid:
                raise ValueError("invalid usage or response id")
            ts = datetime.fromisoformat(obj["timestamp"].replace("Z", "+00:00"))
            day = ts.astimezone(self._tz).date()
            fields = ("input_tokens", "output_tokens", "cache_write_input_tokens", "cached_input_tokens")
            if any(name not in usage for name in fields):
                logger.warning("codex usage: missing token fields default to zero")
            inp, out, cw, cr = (_int(usage.get(name)) for name in fields)
            if not self.buckets.accept(rid, day):
                return
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
            logger.warning("codex usage: skipping malformed record")
            return
        self.buckets.add(key, day, ctx.get("model", ""), [inp - cr - cw, out, cw, 0, cr])
