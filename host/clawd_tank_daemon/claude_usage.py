"""Read-only, offline per-project Claude Code token usage aggregation.

Parses ``~/.claude/projects/**/*.jsonl`` incrementally into daily buckets.
Blocking: call ``refresh()`` from a worker thread (``asyncio.to_thread``).
"""

import json
import logging
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# bucket value layout: [input, output, cache_write_5m, cache_write_1h, cache_read]
_IN, _OUT, _CW5, _CW1, _CR = range(5)

# USD per MTok: (input, output, cache write 5m, cache write 1h, cache read).
# Source: https://platform.claude.com/docs/en/about-claude/pricing, as of 2026-10-13.
# Keys are version-specific prefixes; the longest match wins, so an unlisted new
# version is unpriced instead of borrowing a sibling's price. Claude Haiku 5.5 is
# deliberately absent: its price depends on per-request prompt length (>100k),
# which daily buckets cannot reproduce. Sonnet >200K surcharge is not modeled.
PRICES: Dict[str, Tuple[float, float, float, float, float]] = {
    "claude-fable-5-1": (10, 50, 12.5, 20, 0.25),
    "claude-fable-5": (10, 50, 12.5, 20, 1),
    "claude-opus-5-5": (4, 20, 5, 8, 0.20),
    "claude-opus-5": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-8": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-7": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-6": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-5": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-1": (15, 75, 18.75, 30, 1.50),
    "claude-opus-4-2025": (15, 75, 18.75, 30, 1.50),
    "claude-sonnet-5-5": (2, 10, 2.5, 4, 0.10),
    "claude-sonnet-5": (2, 10, 2.5, 4, 0.20),
    "claude-sonnet-4-6": (3, 15, 3.75, 6, 0.30),
    "claude-sonnet-4-5": (3, 15, 3.75, 6, 0.30),
    "claude-sonnet-4-2025": (3, 15, 3.75, 6, 0.30),
    "claude-haiku-4-5": (1, 5, 1.25, 2, 0.10),
    "claude-3-5-haiku": (0.80, 4, 1, 1.60, 0.08),
}

_project_keys: Dict[str, str] = {}


def _price(model: str) -> Optional[Tuple[float, float, float, float, float]]:
    best = max((k for k in PRICES if model.startswith(k)), key=len, default=None)
    return PRICES[best] if best else None


def project_key(cwd: str) -> str:
    """Git root of ``cwd`` (dir or file ``.git``), else ``cwd`` verbatim."""
    cached = _project_keys.get(cwd)
    if cached is not None:
        return cached
    key = cwd
    path = Path(cwd)
    if path.is_absolute():
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                key = str(candidate)
                break
    _project_keys[cwd] = key
    return key


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class ClaudeUsageReader:
    def __init__(self, root: Path, tz: Optional[tzinfo] = None, retention_days: int = 62):
        self._root = Path(root)
        self._tz = tz
        self._retention = timedelta(days=retention_days)
        self._offsets: Dict[Path, int] = {}
        self._buckets: Dict[Tuple[str, date, str], List[int]] = {}
        self._seen: Dict[Tuple[str, str], date] = {}
        self._newest: Optional[date] = None

    # -- ingest -----------------------------------------------------------

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
        self._prune()

    def _read_file(self, path: Path) -> None:
        if not path.is_file():
            return
        size = path.stat().st_size
        offset = self._offsets.get(path, 0)
        if size < offset:
            offset = 0
        if size == offset:
            self._offsets[path] = offset
            return
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
        end = data.rfind(b"\n")
        if end < 0:
            return  # only a partial line so far
        for raw in data[: end + 1].splitlines():
            self._ingest(raw)
        self._offsets[path] = offset + end + 1

    def _ingest(self, raw: bytes) -> None:
        try:
            obj = json.loads(raw)
            msg = obj["message"]
            usage = msg["usage"]
            ts = datetime.fromisoformat(obj["timestamp"].replace("Z", "+00:00"))
            day = ts.astimezone(self._tz).date()
            cwd = obj["cwd"]
            if not isinstance(usage, dict) or not isinstance(cwd, str):
                return
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        if self._newest is not None and day < self._newest - self._retention:
            return
        dedup = (str(msg.get("id")), str(obj.get("requestId")))
        if dedup in self._seen:
            return
        self._seen[dedup] = day
        cc = usage.get("cache_creation")
        cc = cc if isinstance(cc, dict) else None
        if cc is not None:
            cw5 = _int(cc.get("ephemeral_5m_input_tokens"))
            cw1 = _int(cc.get("ephemeral_1h_input_tokens"))
        else:
            cw5, cw1 = _int(usage.get("cache_creation_input_tokens")), 0
        model = msg.get("model")
        bucket = self._buckets.setdefault(
            (project_key(cwd), day, model if isinstance(model, str) else ""), [0] * 5
        )
        bucket[_IN] += _int(usage.get("input_tokens"))
        bucket[_OUT] += _int(usage.get("output_tokens"))
        bucket[_CW5] += cw5
        bucket[_CW1] += cw1
        bucket[_CR] += _int(usage.get("cache_read_input_tokens"))
        if self._newest is None or day > self._newest:
            self._newest = day

    def _prune(self) -> None:
        if self._newest is None:
            return
        cutoff = self._newest - self._retention
        self._buckets = {k: v for k, v in self._buckets.items() if k[1] >= cutoff}
        self._seen = {k: d for k, d in self._seen.items() if d >= cutoff}

    def _oldest_bucket_dates(self) -> List[date]:
        return [k[1] for k in self._buckets]

    # -- query ------------------------------------------------------------

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
            _apply_cost(projects[key][name], per_model)
        return sorted(projects.values(), key=lambda p: p["key"])


def _apply_cost(window: dict, per_model: Dict[str, List[int]]) -> None:
    total, priced, unpriced = 0.0, False, []
    for model, t in per_model.items():
        if not any(t):
            continue
        price = _price(model)
        if price is None:
            unpriced.append(model)
            continue
        priced = True
        total += sum(n * rate for n, rate in zip(t, price)) / 1_000_000
    window["cost"] = round(total, 6) if priced else None
    window["cost_partial"] = bool(unpriced)
    if unpriced:
        window["unpriced"] = sorted(unpriced)


def _empty() -> dict:
    return {"in": 0, "out": 0, "cw": 0, "cr": 0, "cost": 0.0, "cost_partial": False}
