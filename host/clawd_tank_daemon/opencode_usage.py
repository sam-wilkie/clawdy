"""Read-only OpenCode SQLite usage; call refresh via asyncio.to_thread."""

import json
import logging
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Optional

from .usage_common import UsageBuckets, project_key

logger = logging.getLogger(__name__)


class OpenCodeUsageReader:
    cost_kind = "reported"

    def __init__(self, path: Path, tz: Optional[tzinfo] = None,
                 temp_root: Optional[str] = None):
        self._path, self._tz, self._temp_root = Path(path), tz, temp_root
        self._state = self._empty()
        self.status = "absent"
        self._failures = set()

    def _empty(self):
        return UsageBuckets(self._tz, 62, {}), UsageBuckets(self._tz, 62, {})

    def refresh(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(timezone.utc)
        try:
            if not self._path.exists():
                self._state = self._empty()
                self.status = "absent"
                return
            try:
                buckets, costs = self._read(now)
            except sqlite3.Error as exc:
                code = getattr(exc, "sqlite_errorcode", 0) & 0xff
                if (code not in (sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_READONLY)
                        or self._wal_exists()):
                    raise
                buckets, costs = self._read(now, immutable=True)
            self._state = buckets, costs
            self.status = "ok"
        except (sqlite3.Error, OSError) as exc:
            self.status = "error"
            signature = (type(exc).__name__, getattr(exc, "sqlite_errorcode", None), str(exc))
            if signature not in self._failures:
                self._failures.add(signature)
                logger.warning("opencode usage: %s", exc)

    def _wal_exists(self):
        return self._path.with_name(self._path.name + "-wal").exists()

    def _read(self, now, immutable=False):
        uri = self._path.resolve().as_uri() + "?mode=ro"
        if immutable:
            uri += "&immutable=1"
        elif not self._wal_exists():
            # Plain ro can create WAL/SHM. nolock prevents that, causing WAL
            # reads to fail with CANTOPEN and take the guarded immutable retry.
            uri += "&nolock=1"
        buckets, costs = self._empty()
        cutoff = int((now - timedelta(days=62)).timestamp() * 1000)
        with closing(sqlite3.connect(uri, uri=True, timeout=0.5)) as connection:
            connection.text_factory = bytes
            rows = connection.execute("SELECT data FROM message WHERE time_created >= ?", (cutoff,))
            for (raw,) in rows:
                try:
                    msg = json.loads(raw)
                    if msg["role"] != "assistant":
                        continue
                    key = project_key(msg["path"]["cwd"], self._temp_root)
                    if key is None:
                        continue
                    day = datetime.fromtimestamp(msg["time"]["created"] / 1000,
                                                 timezone.utc).astimezone(self._tz).date()
                    tokens = msg["tokens"]
                    cache = tokens.get("cache", {})
                    vec = [tokens.get("input", 0), tokens.get("output", 0),
                           cache.get("write", 0), 0, cache.get("read", 0)]
                    if any(not isinstance(n, int) or isinstance(n, bool) for n in vec):
                        continue
                    cost = msg.get("cost")
                    reported = (isinstance(cost, (int, float)) and not isinstance(cost, bool)
                                and math.isfinite(cost))
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
                    continue
                buckets.add(key, day, "", vec)
                costs.add(key, day, "", [cost if reported else 0.0, int(not reported), 0, 0, 0])
        return buckets, costs

    def snapshot(self, now: datetime) -> list[dict]:
        buckets, cost_buckets = self._state
        projects = buckets.snapshot(now)
        costs = {p["key"]: p for p in cost_buckets.snapshot(now)}
        for project in projects:
            for name in ("today", "7d", "30d", "month"):
                window, reported = project[name], costs[project["key"]][name]
                window["cost"] = round(reported["in"], 6)
                window["cost_partial"] = bool(reported["out"])
                window.pop("unpriced", None)
        return projects
