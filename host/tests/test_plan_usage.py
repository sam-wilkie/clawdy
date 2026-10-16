"""Read-only subscription cache contracts."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from clawd_tank_daemon import plan_usage as plan

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


def test_claude_limits(tmp_path):
    path = tmp_path / "cache.json"
    assert plan.read_claude_plan(path, NOW)["plan"] == {"status": "no_data"}
    for data in ({}, {"rate_limits": None}, {"rate_limits": {"five_hour": []}}):
        path.write_text(json.dumps(data))
        assert plan.read_claude_plan(path, NOW)["billing"] == "payg"
    for pct in (62, -1, "62", True, float("nan")):
        path.write_text(json.dumps({"rate_limits": {"five_hour": {
            "used_percentage": pct, "resets_at": 1800000000},
            "seven_day": {"used_percentage": 38}}}))
        result = plan.read_claude_plan(path, NOW)
        limits = result["plan"]["limits"]
        assert result["billing"] == "plan"
        assert limits[-1]["id"] == "weekly" and limits[-1]["used_pct"] == 38
        assert len(limits) == (2 if pct == 62 else 1)
        if len(limits) == 2:
            assert limits[0]["window_min"] == 300
            assert datetime.fromisoformat(limits[0]["resets_at"]).timestamp() == 1800000000


def make_db(path, used=340, timestamp=100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        state = {"kiro.resourceNotifications.usageState": {"timestamp": timestamp,
                 "usageBreakdowns": [{"type": "CREDIT", "currentUsage": used,
                 "usageLimit": 1000, "resetDate": "2026-10-28T00:00:00Z"}]}}
        db.executemany("INSERT INTO ItemTable VALUES (?, ?)", [
            ("kiro.kiroAgent", json.dumps(state)), ("kiro.kiroagent", "malformed"),
            ("secret-storage", "DO NOT READ")])
    db.close()
    return path


def test_kiro_paths_newest_and_security(tmp_path, monkeypatch):
    user = tmp_path / "Kiro/User"
    first = make_db(user / "globalStorage/state.vscdb")
    newest = make_db(user / "profiles/a/globalStorage/state.vscdb", 500, 200)
    env = {"APPDATA": str(tmp_path)}
    paths = plan.kiro_state_paths(env=env, home=tmp_path, platform="win32")
    assert set(paths) == {first, newest}
    before = {p: p.read_bytes() for p in user.rglob("*") if p.is_file()}
    listing = set(user.rglob("*"))
    connect = sqlite3.connect
    queries = []
    def traced(database, **kw):
        assert "mode=ro" in database and kw == {"uri": True, "timeout": 0.5}
        db = connect(database, **kw)
        db.set_trace_callback(queries.append)
        return db
    monkeypatch.setattr(plan.sqlite3, "connect", traced)
    result = plan.read_kiro_plan(paths, NOW)
    assert result["plan"]["credits"] == {"used": 500, "limit": 1000}
    assert result["plan"]["limits"][0]["used_pct"] == 50
    assert set(queries) == {"SELECT value FROM ItemTable WHERE key IN ('kiro.kiroAgent', 'kiro.kiroagent')"}
    assert listing == set(user.rglob("*"))
    assert before == {p: p.read_bytes() for p in before}
    override = plan.kiro_state_paths(env={"CLAWDY_KIRO_STATE_DB": str(first)}, home=tmp_path)
    assert override == [first]
    assert plan.read_kiro_plan(override, NOW)["plan"]["limits"][0]["used_pct"] == 34
    assert plan.read_kiro_plan([tmp_path / "missing"], NOW) == {"status": "absent"}
    with first.open("r+b") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    assert plan.read_kiro_plan([first], NOW)["plan"] == {"status": "no_data"}



@pytest.mark.parametrize("wal", [False, True])
def test_kiro_immutable_retry_guard(tmp_path, monkeypatch, wal):
    path = make_db(tmp_path / "state.vscdb")
    if wal:
        path.with_name(path.name + "-wal").touch()
    attempts = []
    def denied(database, **kwargs):
        attempts.append(database)
        error = sqlite3.OperationalError("cannot open")
        error.sqlite_errorcode = sqlite3.SQLITE_CANTOPEN
        raise error
    monkeypatch.setattr(plan.sqlite3, "connect", denied)
    assert plan.read_kiro_plan([path], NOW)["plan"] == {"status": "no_data"}
    assert len(attempts) == (1 if wal else 2)
    assert all("immutable=1" not in uri for uri in attempts[:1])
    if not wal:
        assert "immutable=1" in attempts[1]
