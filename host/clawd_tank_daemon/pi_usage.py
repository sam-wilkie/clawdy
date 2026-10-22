"""Read-only Pi usage and reported cost; run refresh via asyncio.to_thread."""

import json
import logging
import math
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Optional

from .usage_common import JsonlTailReader, UsageBuckets, project_key

logger = logging.getLogger(__name__)


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class PiUsageReader(JsonlTailReader):
    cost_kind = "reported"

    def __init__(
        self,
        root: Path,
        tz: Optional[tzinfo] = None,
        retention_days: int = 62,
        temp_root: Optional[str] = None,
    ):
        super().__init__(root, tz, retention_days, temp_root)
        # Reuse the same window and retention rules for [reported USD, missing count].
        self._costs = UsageBuckets(tz, retention_days, {})
        self.status = "absent"

    def refresh(self) -> None:
        try:
            self.status = "ok" if self._root.is_dir() else "absent"
            if self.status == "ok":
                super().refresh()
                self._costs.prune()
        except OSError:
            self.status = "error"
            logger.warning("pi usage: cannot read %s", self._root, exc_info=True)

    def _ingest(self, raw: bytes, ctx: dict) -> None:
        try:
            obj = json.loads(raw)
            if obj.get("type") == "session":
                cwd = obj.get("cwd")
                ctx["key"] = project_key(cwd, self._temp_root) if isinstance(cwd, str) else None
                return
            if obj.get("type") != "message":
                return
            msg = obj["message"]
            if msg.get("role") != "assistant":
                return
            key = ctx.get("key")
            if key is None:
                if "key" not in ctx:
                    logger.warning("pi usage: skipping message without session record")
                return
            usage = msg["usage"]
            stamp = msg.get("timestamp", obj.get("timestamp"))
            ts = (datetime.fromtimestamp(stamp / 1000, timezone.utc)
                  if isinstance(stamp, (int, float)) else
                  datetime.fromisoformat(stamp.replace("Z", "+00:00")))
            day = ts.astimezone(self._tz).date()
            if any(n not in usage for n in ("input", "output", "cacheWrite", "cacheRead")):
                logger.warning("pi usage: missing token fields default to zero")
            vec = [_int(usage.get(n)) for n in ("input", "output", "cacheWrite")]
            vec += [0, _int(usage.get("cacheRead"))]
            cost = usage.get("cost")
            cost = cost.get("total") if isinstance(cost, dict) else None
            reported = (isinstance(cost, (int, float)) and not isinstance(cost, bool)
                        and math.isfinite(cost))
            mid = obj.get("id")
            if not self.buckets.accept(mid if mid is not None else object(), day):
                return
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
            logger.warning("pi usage: skipping malformed record")
            return
        self.buckets.add(key, day, "", vec)
        self._costs.add(key, day, "", [cost if reported else 0.0, int(not reported), 0, 0, 0])

    def snapshot(self, now: datetime) -> list[dict]:
        projects = super().snapshot(now)
        costs = {p["key"]: p for p in self._costs.snapshot(now)}
        for project in projects:
            for name in ("today", "7d", "30d", "month"):
                window = project[name]
                reported = costs[project["key"]][name]
                window["cost"] = reported["in"]
                window["cost_partial"] = bool(reported["out"])
                window.pop("unpriced", None)
        return projects
