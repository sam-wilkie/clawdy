"""Read local subscription caches without changing files or exposing secrets."""
import json
import math
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _object(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def _reset(value):
    try:
        if _number(value):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        parsed = datetime.fromisoformat(value)
        return parsed.isoformat() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def read_claude_plan(cache_path, now):
    try:
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    rates = _object(_object(data).get("rate_limits"))
    limits = []
    for key, name, label in (("five_hour", "session", "5h session"),
                             ("seven_day", "weekly", "Weekly")):
        row = _object(rates.get(key))
        pct = row.get("used_percentage")
        if _number(pct):
            limit = dict(id=name, label=label, used_pct=pct, resets_at=_reset(row.get("resets_at")))
            if name == "session":
                limit["window_min"] = 300
            limits.append(limit)
    return {"status": "ok", "billing": "plan" if limits else "payg",
            "plan": {"status": "ok", "limits": limits} if limits else {"status": "no_data"}}


def kiro_state_paths(env=None, home=None, platform=None):
    env, home, platform = os.environ if env is None else env, home or Path.home(), platform or sys.platform
    if env.get("CLAWDY_KIRO_STATE_DB"):
        return [Path(env["CLAWDY_KIRO_STATE_DB"])]
    base = (Path(env.get("APPDATA") or home / "AppData/Roaming") if platform == "win32" else
            home / "Library/Application Support" if platform == "darwin" else
            Path(env.get("XDG_CONFIG_HOME") or home / ".config"))
    user = base / "Kiro/User"
    return [user / "globalStorage/state.vscdb", *user.glob("profiles/*/globalStorage/state.vscdb")]


def _kiro_rows(path, immutable=False):
    if Path(str(path) + "-wal").exists() and not Path(str(path) + "-shm").exists():
        # A ro WAL open would create the missing -shm beside Kiro's DB; skip this pass instead.
        raise RuntimeError("Kiro state DB has a WAL file without its shared-memory file")
    uri = path.resolve().as_uri() + "?mode=ro"
    if immutable:
        uri += "&immutable=1"
    elif not Path(str(path) + "-wal").exists():
        # Like OpenCode, avoid creating WAL/SHM before the guarded retry.
        uri += "&nolock=1"
    with closing(sqlite3.connect(uri, uri=True, timeout=0.5)) as db:
        return db.execute("SELECT value FROM ItemTable WHERE key IN ('kiro.kiroAgent', 'kiro.kiroagent')").fetchall()


def read_kiro_plan(paths, now):
    found, latest, timestamp, skipped = False, None, -1, False
    for path in paths:
        path = Path(path)
        try:
            if not path.is_file():
                continue
            found = True
            if path.stat().st_size > 64 * 1024 * 1024:
                continue
            try:
                rows = _kiro_rows(path)
            except RuntimeError:
                skipped = True  # this DB only; other profiles may still be readable
                continue
            except sqlite3.Error as exc:
                if ((getattr(exc, "sqlite_errorcode", 0) & 0xff) not in
                        (sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_READONLY)
                        or Path(str(path) + "-wal").exists()):
                    raise
                rows = _kiro_rows(path, immutable=True)
            for (raw,) in rows:
                try:
                    state = _object(_object(json.loads(raw)).get("kiro.resourceNotifications.usageState"))
                    breakdowns = state.get("usageBreakdowns")
                    if not isinstance(breakdowns, list):
                        continue
                    for row in breakdowns:
                        row = _object(row)
                        used, limit = row.get("currentUsage"), row.get("usageLimit")
                        stamp = state.get("timestamp")
                        stamp = stamp if _number(stamp) else 0
                        if (row.get("type") != "CREDIT" or not _number(used) or
                                not _number(limit) or limit <= 0 or stamp <= timestamp):
                            continue
                        pct = used / limit * 100
                        if not math.isfinite(pct):
                            continue
                        latest = {"status": "ok", "credits": {"used": used, "limit": limit},
                                  "limits": [dict(id="credits", label="Cycle credits", used_pct=pct,
                                                  resets_at=_reset(row.get("resetDate")))]}
                        timestamp = stamp
                except (ValueError, TypeError, OverflowError):
                    continue
        except (OSError, sqlite3.Error):
            continue
    if latest is None and skipped:
        # Nothing readable this pass; raising keeps the daemon's last good plan.
        raise RuntimeError("Kiro state DB has a WAL file without its shared-memory file")
    return ({"status": "ok", "billing": "plan", "plan": latest or {"status": "no_data"}}
            if found else {"status": "absent"})
