"""Read local subscription caches without changing files or exposing secrets."""
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def find_codex_exe(env=None, home=None, platform=None):
    env, home, platform = os.environ if env is None else env, Path(home or Path.home()), platform or sys.platform
    def native(path):
        return path.is_absolute() and path.suffix.lower() not in (".cmd", ".bat", ".ps1") and path.is_file()
    def directories(root):
        try:
            return sorted((p for p in root.iterdir() if p.is_dir()), reverse=True,
                          key=lambda p: [(s.isdigit(), int(s) if s.isdigit() else s.casefold())
                                         for s in re.split(r"(\d+)", p.name)])
        except OSError:
            return []
    if env.get("CLAWDY_CODEX_BIN"):
        path = Path(env["CLAWDY_CODEX_BIN"])
        return str(path) if native(path) else None
    binary = "codex.exe" if platform == "win32" else "codex"
    paths = [Path(p) for p in (env.get("PATH") or env.get("Path", "")).split(";" if platform == "win32" else ":") if p]
    candidates = [p / binary for p in paths]
    releases = Path(env.get("CODEX_HOME") or home / ".codex") / "packages/app-server-daemon/releases"
    for directory in directories(releases):
        candidates.extend((directory / "bin" / binary, directory / binary))
    if platform == "win32":
        local = Path(env.get("LOCALAPPDATA") or home / "AppData/Local")
        candidates.extend(p / binary for p in directories(local / "OpenAI/Codex/bin"))
        roots = ([Path(env["APPDATA"]) / "npm"] if env.get("APPDATA") else []) + paths
        for root in roots:
            package = root / "node_modules/@openai/codex"
            for pkg in [package, *directories(package / "node_modules/@openai")]:
                candidates.extend(p / "codex" / binary for p in directories(pkg / "vendor"))
    else:
        candidates.extend((home / ".local/bin/codex", Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex")))
        if platform == "darwin":
            candidates.append(Path("/Applications/Codex.app/Contents/Resources/codex"))
    return next((str(p) for p in candidates if native(p)), None)


CODEX_CACHE_S = 300        # the app-server is a heavy spawn; quotas move slowly
CODEX_TIMEOUT_S = 15       # hard kill so a hung server cannot stall the refresh loop
CODEX_MAX_LINE = 65536     # one JSON-RPC message per line; we read one byte more to detect longer ones
CODEX_EXIT_GRACE_S = 0.5   # time to exit after stdin closes before we kill it
JSONRPC_METHOD_NOT_FOUND = -32601


class CodexPlanSource:
    """Read account quotas with bounded process lifetime and a five-minute cache."""
    def __init__(self, exe_finder=find_codex_exe, popen=subprocess.Popen, timeout_s=CODEX_TIMEOUT_S):
        self._find, self._popen, self._timeout = exe_finder, popen, timeout_s
        self._last, self._result, self._failed = None, None, False

    def refresh(self, now):
        if self._last is None or (now - self._last).total_seconds() >= CODEX_CACHE_S:
            self._last = now
            try:
                self._result = self._read()
                self._failed = False
            except Exception:
                self._failed = True
        if self._failed:
            # Never expose protocol payloads in the daemon's failure signature.
            raise RuntimeError("Codex plan read failed") from None
        return self._result

    def _read(self):
        billing = (self._result or {}).get("billing", "plan")
        exe = self._find()
        if not exe:
            return {"status": "ok", "billing": billing, "plan": {"status": "not_installed"}}
        child = self._popen([exe, "app-server", "--listen", "stdio://"], shell=False,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        expired = threading.Event()
        def expire():
            expired.set()
            try:
                child.kill()
            except OSError:
                pass  # The child may already have exited.
        timer = threading.Timer(self._timeout, expire)
        timer.daemon = True
        def send(message):
            child.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
            child.stdin.flush()
        def request(identifier, method, params=None):
            send({"id": identifier, "method": method, "params": params or {}})
            while not expired.is_set():
                line = child.stdout.readline(CODEX_MAX_LINE + 1)
                if expired.is_set() or not line or len(line) > CODEX_MAX_LINE or not line.endswith(b"\n"):
                    raise ValueError("Invalid Codex line")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Invalid Codex message")
                if "method" in message:
                    if "id" in message:
                        # The server may ask us things (approvals, input); this read-only client answers none.
                        send({"id": message["id"], "error": {"code": JSONRPC_METHOD_NOT_FOUND, "message": "Unsupported client request"}})
                    continue
                if message.get("id") == identifier:
                    if "error" in message or not isinstance(message.get("result"), dict):
                        raise ValueError("Invalid Codex result")
                    return message["result"]
            raise TimeoutError("Codex plan timeout")
        timer.start()
        try:
            request(0, "initialize", {"clientInfo": {"name": "clawdy", "version": "0.0.1"}})
            send({"method": "initialized", "params": {}})
            account = request(1, "account/read", {"refreshToken": False}).get("account")
            if account is None:
                return {"status": "ok", "billing": "plan", "plan": {"status": "signed_out"}}
            if not isinstance(account, dict) or account.get("type") not in ("apiKey", "chatgpt"):
                raise ValueError("Invalid Codex account")
            if account["type"] == "apiKey":
                return {"status": "ok", "billing": "payg"}
            rates = request(2, "account/rateLimits/read")
            bucket = _object(rates.get("rateLimitsByLimitId")).get("codex")
            legacy = _object(rates.get("rateLimits"))
            bucket = _object(bucket or (legacy if legacy.get("limitId") in (None, "codex") else {}))
            limits = []
            for key, name in (("primary", "primary"), ("secondary", "weekly")):
                row = _object(bucket.get(key))
                if not _number(row.get("usedPercent")):
                    continue
                window = row.get("windowDurationMins")
                label = f"{window / 60:g}h window" if name == "primary" and _number(window) else "Weekly" if name == "weekly" else "Primary"
                limit = dict(id=name, label=label, used_pct=row["usedPercent"], resets_at=_reset(row.get("resetsAt")))
                if _number(window):
                    limit["window_min"] = window
                limits.append(limit)
            credits = _object(rates.get("rateLimitResetCredits")).get("availableCount")
            return {"status": "ok", "billing": "plan", "plan": {
                "status": "ok" if limits else "no_data", "limits": limits,
                "reset_credits": credits if type(credits) is int and credits >= 0 else None}}
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass
            try:
                child.wait(timeout=CODEX_EXIT_GRACE_S)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            finally:
                timer.cancel()
                timer.join()
                child.stdout.close()


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
