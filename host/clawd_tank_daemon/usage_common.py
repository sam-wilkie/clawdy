"""Shared layer for the per-agent usage readers (Claude, Codex, OpenCode, Pi).

Holds the one project-key rule, longest-prefix price lookup, the incremental
JSONL tail reader and the daily-bucket aggregation. Blocking: call
``refresh()`` from a worker thread (``asyncio.to_thread``).
"""

import logging
import os
import tempfile
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Dict, Hashable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# bucket value layout: [input, output, cache_write_5m, cache_write_1h, cache_read]
_IN, _OUT, _CW5, _CW1, _CR = range(5)

Prices = Dict[str, Tuple[float, float, float, float, float]]

_project_keys: Dict[Tuple[str, Optional[str]], Optional[str]] = {}


def price_lookup(prices: Prices, model: str) -> Optional[Tuple[float, float, float, float, float]]:
    best = max((k for k in prices if model.startswith(k)), key=len, default=None)
    return prices[best] if best else None


def _under(path: Path, root: str) -> bool:
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def project_key(cwd: str, temp_root: Optional[str] = None) -> Optional[str]:
    """Git root of ``cwd`` (dir or file ``.git``).

    None when ``cwd`` is relative, has no git ancestor, or is under ``temp_root``
    (default: the OS temp dir). Such sessions are excluded from all totals.
    """
    root = None if temp_root is None else str(temp_root)
    cache_key = (cwd, root)
    if cache_key in _project_keys:
        return _project_keys[cache_key]
    key = None
    path = Path(cwd)
    if path.is_absolute() and not _under(path, root or tempfile.gettempdir()):
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                key = str(candidate)
                break
    _project_keys[cache_key] = key
    return key


def _empty() -> dict:
    return {"in": 0, "out": 0, "cw": 0, "cr": 0, "cost": 0.0, "cost_partial": False}


def _apply_cost(window: dict, per_model: Dict[str, List[int]], prices: Prices) -> None:
    total, priced, unpriced = 0.0, False, []
    for model, t in per_model.items():
        if not any(t):
            continue
        price = price_lookup(prices, model)
        if price is None:
            unpriced.append(model)
            continue
        priced = True
        total += sum(n * rate for n, rate in zip(t, price)) / 1_000_000
    window["cost"] = round(total, 6) if priced else None
    window["cost_partial"] = bool(unpriced)
    if unpriced:
        window["unpriced"] = sorted(unpriced)


class UsageBuckets:
    """Daily ``(key, day, model) -> [in, out, cw5, cw1, cr]`` buckets with windows and cost."""

    def __init__(self, tz: Optional[tzinfo], retention_days: int, prices: Prices):
        self._tz = tz
        self._retention = timedelta(days=retention_days)
        self._prices = prices
        self._buckets: Dict[Tuple[str, date, str], List[int]] = {}
        self._seen: Dict[Hashable, date] = {}
        self._newest: Optional[date] = None

    def accept(self, dedup: Hashable, day: date) -> bool:
        """True once per ``dedup`` id, and only for days inside the retention window."""
        if self._newest is not None and day < self._newest - self._retention:
            return False
        if dedup in self._seen:
            return False
        self._seen[dedup] = day
        return True

    def add(self, key: str, day: date, model: str, vec: List[int]) -> None:
        bucket = self._buckets.setdefault((key, day, model), [0] * 5)
        for i, n in enumerate(vec):
            bucket[i] += n
        if self._newest is None or day > self._newest:
            self._newest = day

    def prune(self) -> None:
        if self._newest is None:
            return
        cutoff = self._newest - self._retention
        self._buckets = {k: v for k, v in self._buckets.items() if k[1] >= cutoff}
        self._seen = {k: d for k, d in self._seen.items() if d >= cutoff}

    def oldest_dates(self) -> List[date]:
        return [k[1] for k in self._buckets]

    def snapshot(self, now: datetime) -> List[dict]:
        today = now.astimezone(self._tz).date()
        windows = {
            "today": lambda d: d == today,
            "7d": lambda d: today - timedelta(days=6) <= d <= today,
            "30d": lambda d: today - timedelta(days=29) <= d <= today,
            "month": lambda d: d.replace(day=1) == today.replace(day=1) and d <= today,
        }
        projects: Dict[str, dict] = {}
        # (project, window) -> model -> summed tokens
        shares: Dict[Tuple[str, str], Dict[str, List[int]]] = {}
        for (key, day, model), v in self._buckets.items():
            for name, inside in windows.items():
                if not inside(day):
                    continue
                proj = projects.setdefault(
                    key, {"key": key, "label": Path(key).name or key, **{w: _empty() for w in windows}}
                )
                w = proj[name]
                w["in"] += v[_IN]
                w["out"] += v[_OUT]
                w["cw"] += v[_CW5] + v[_CW1]
                w["cr"] += v[_CR]
                acc = shares.setdefault((key, name), {}).setdefault(model, [0] * 5)
                for i, n in enumerate(v):
                    acc[i] += n
        for (key, name), per_model in shares.items():
            _apply_cost(projects[key][name], per_model, self._prices)
        return sorted(projects.values(), key=lambda p: p["key"])


class JsonlTailReader:
    """Incrementally reads ``root/**/*.jsonl``; subclasses implement ``_ingest``.

    ``_ingest(raw, ctx)`` gets one complete line plus a per-file dict that
    survives across passes and is reset when the file shrinks.
    """

    def __init__(
        self,
        root: Path,
        tz: Optional[tzinfo] = None,
        retention_days: int = 62,
        temp_root: Optional[str] = None,
        prices: Optional[Prices] = None,
    ):
        self._root = Path(root)
        self._tz = tz
        self._temp_root = temp_root
        self.buckets = UsageBuckets(tz, retention_days, prices or {})
        self._offsets: Dict[Path, int] = {}
        self._contexts: Dict[Path, dict] = {}

    def refresh(self) -> None:
        try:
            files = sorted(self._root.rglob("*.jsonl"))
        except OSError:
            logger.warning("usage: cannot scan %s", self._root, exc_info=True)
            return
        for path in files:
            try:
                self._read_file(path)
            except Exception:
                logger.warning("usage: skipping unreadable %s", path, exc_info=True)
        self.buckets.prune()

    def _read_file(self, path: Path) -> None:
        if not path.is_file():
            return
        size = path.stat().st_size
        offset = self._offsets.get(path, 0)
        if size < offset:
            offset = 0
            self._contexts.pop(path, None)
        if size == offset:
            self._offsets[path] = offset
            return
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
        end = data.rfind(b"\n")
        if end < 0:
            return  # only a partial line so far
        ctx = self._contexts.setdefault(path, {})
        for raw in data[: end + 1].splitlines():
            self._ingest(raw, ctx)
        self._offsets[path] = offset + end + 1

    def _ingest(self, raw: bytes, ctx: dict) -> None:
        raise NotImplementedError

    def snapshot(self, now: datetime) -> List[dict]:
        return self.buckets.snapshot(now)
