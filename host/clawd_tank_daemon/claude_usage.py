"""Read-only, offline per-project Claude Code token usage aggregation.

Parses ``~/.claude/projects/**/*.jsonl`` incrementally into daily buckets.
Blocking: call ``refresh()`` from a worker thread (``asyncio.to_thread``).
"""

import json
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Optional

from .usage_common import JsonlTailReader, Prices, project_key

# USD per MTok: (input, output, cache write 5m, cache write 1h, cache read).
# Source: https://platform.claude.com/docs/en/about-claude/pricing, as of 2026-10-13.
# Keys are version-specific prefixes; the longest match wins, so an unlisted new
# version is unpriced instead of borrowing a sibling's price. Claude Haiku 5.5 is
# deliberately absent: its price depends on per-request prompt length (>100k),
# which daily buckets cannot reproduce. Sonnet >200K surcharge is not modeled.
PRICES: Prices = {
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

def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class ClaudeUsageReader(JsonlTailReader):
    def __init__(
        self,
        root: Path,
        tz: Optional[tzinfo] = None,
        retention_days: int = 62,
        temp_root: Optional[str] = None,
    ):
        super().__init__(root, tz, retention_days, temp_root, PRICES)

    def _oldest_bucket_dates(self):
        return self.buckets.oldest_dates()

    def _ingest(self, raw: bytes, ctx: dict) -> None:
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
        key = project_key(cwd, self._temp_root)
        if key is None or not self.buckets.accept((str(msg.get("id")), str(obj.get("requestId"))), day):
            return
        cc = usage.get("cache_creation")
        cc = cc if isinstance(cc, dict) else None
        if cc is not None:
            cw5 = _int(cc.get("ephemeral_5m_input_tokens"))
            cw1 = _int(cc.get("ephemeral_1h_input_tokens"))
        else:
            cw5, cw1 = _int(usage.get("cache_creation_input_tokens")), 0
        model = msg.get("model")
        self.buckets.add(
            key,
            day,
            model if isinstance(model, str) else "",
            [
                _int(usage.get("input_tokens")),
                _int(usage.get("output_tokens")),
                cw5,
                cw1,
                _int(usage.get("cache_read_input_tokens")),
            ],
        )
