"""OpenCode contract, using local WAL fixtures and committed assistant rows."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from clawd_tank_daemon.opencode_usage import OpenCodeUsageReader

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def message(cwd, days=0, cost=0.1, role="assistant"):
    # Inspected real DB read-only 2026-10-16; directory listing unchanged.
    # message: id TEXT PK, session_id TEXT, time_created/time_updated INTEGER,
    # data TEXT. JSON: path.cwd, time.created (epoch ms), role, numeric cost,
    # tokens.input/output/cache.read/cache.write. part has message_id + data.
    return {"role": role, "path": {"cwd": str(cwd)}, "cost": cost,
            "time": {"created": int((NOW - timedelta(days=days)).timestamp() * 1000)},
            "tokens": {"input": 10, "output": 20, "cache": {"read": 40, "write": 30}}}


def insert(c, mid, obj):
    c.execute("INSERT INTO message VALUES (?, 's', ?, ?, ?)",
              (mid, obj["time"]["created"], obj["time"]["created"], json.dumps(obj)))


@pytest.fixture
def db(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    path = tmp_path / "opencode.db"
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
              "time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL)")
    insert(c, "a", message(repo))
    c.commit()
    yield path, c, repo
    c.close()


def reader(path, temp_root=None):
    r = OpenCodeUsageReader(path, tz=timezone.utc,
                           temp_root=str(temp_root or path.parent / "fake-tmp"))
    r.refresh(NOW)
    return r


def test_totals_windows_reported_cost_part_ignored_and_update(db):
    path, c, repo = db
    other = path.parent / "other"
    (other / ".git").mkdir(parents=True)
    insert(c, "b", message(repo, days=20, cost=0.2))
    insert(c, "c", message(other, days=10, cost=0.3))
    insert(c, "user", message(repo, cost=99, role="user"))
    insert(c, "old", message(repo, days=63, cost=99))
    c.execute("UPDATE message SET data=? WHERE id='old'", (json.dumps(message(repo, cost=99)),))
    c.execute("CREATE TABLE part(message_id TEXT, data TEXT)")
    c.execute("INSERT INTO part VALUES ('a', ?)", (json.dumps(message(repo, cost=99)),))
    c.commit()
    r = reader(path)
    snap = {p["key"]: p for p in r.snapshot(NOW)}
    assert r.status == "ok" and r.cost_kind == "reported"
    assert set(snap) == {str(repo), str(other)}
    recent = {"in": 10, "out": 20, "cw": 30, "cr": 40, "cost": 0.1, "cost_partial": False}
    for name in ("today", "7d", "month"):
        assert snap[str(repo)][name] == recent
    assert snap[str(repo)]["30d"] == {**recent, "in": 20, "out": 40, "cw": 60, "cr": 80, "cost": 0.3}
    for name in ("today", "7d"):
        assert snap[str(other)][name] == {**dict.fromkeys(("in", "out", "cw", "cr"), 0),
                                           "cost": 0.0, "cost_partial": False}
    for name in ("30d", "month"):
        assert snap[str(other)][name] == {**recent, "cost": 0.3}
    changed = message(repo, cost=0.123456789)
    changed["tokens"]["input"] = 50
    c.execute("UPDATE message SET data=? WHERE id='a'", (json.dumps(changed),))
    c.commit()
    r.refresh(NOW)
    w = next(p for p in r.snapshot(NOW) if p["key"] == str(repo))["today"]
    assert w == {**recent, "in": 50, "cost": 0.123457}


def test_live_writer_committed_only_within_timeout_and_bytes_unchanged(db):
    path, c, repo = db
    c.execute("BEGIN IMMEDIATE")
    insert(c, "uncommitted", message(repo, cost=99))
    before = {p: p.read_bytes() for p in (path, path.with_name(path.name + "-wal"))}
    start = time.monotonic()
    r = reader(path)
    assert time.monotonic() - start < 0.5
    assert r.status == "ok" and r.snapshot(NOW)[0]["today"]["cost"] == 0.1
    assert c.in_transaction
    assert before == {p: p.read_bytes() for p in before}
    c.rollback()


def test_clean_closed_wal_no_sidecars_and_immutable_retry(db, monkeypatch):
    path, c, _ = db
    c.close()
    before = {p.name: p.read_bytes() for p in path.parent.iterdir() if p.is_file()}
    assert set(before) == {path.name}
    connect, calls = sqlite3.connect, []

    def spy(database, **kwargs):
        calls.append((database, kwargs))
        return connect(database, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    r = reader(path)
    assert r.status == "ok" and r.snapshot(NOW)[0]["today"]["in"] == 10
    assert "mode=ro" in calls[0][0] and "immutable" not in calls[0][0]
    assert all(kwargs == {"uri": True, "timeout": 0.5} for _, kwargs in calls)
    assert any("immutable=1" in uri for uri, _ in calls)
    assert before == {p.name: p.read_bytes() for p in path.parent.iterdir() if p.is_file()}


@pytest.mark.parametrize("good", [False, True])
@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_READONLY])
@pytest.mark.parametrize("wal", [False, True])
def test_failure_keeps_snapshot_and_guards_immutable_retry(db, monkeypatch, caplog, good, code, wal):
    path, c, _ = db
    r = reader(path) if good else OpenCodeUsageReader(path)
    if not wal:
        c.close()
    before, calls = r.snapshot(NOW), []

    def fail(database, **kwargs):
        calls.append(database)
        exc = sqlite3.OperationalError("locked" if code == sqlite3.SQLITE_BUSY else "read only")
        exc.sqlite_errorcode = code
        raise exc

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", fail)
        for _ in range(2):
            r.refresh(NOW)
            assert r.status == "error" and r.snapshot(NOW) == before
    retry = not wal and code == sqlite3.SQLITE_READONLY
    assert len(caplog.records) == 1 and len(calls) == (4 if retry else 2)
    assert all("mode=ro" in uri for uri in calls)
    assert sum("immutable=1" in uri for uri in calls) == (2 if retry else 0)
    r.refresh(NOW)
    assert r.status == "ok"


def test_missing_table_and_column_keep_last_good_and_log_distinct_failures(db, caplog):
    path, c, _ = db
    r = reader(path)
    before = r.snapshot(NOW)
    c.execute("DROP TABLE message")
    c.commit()
    for _ in range(2):
        r.refresh(NOW)
        assert r.status == "error" and r.snapshot(NOW) == before
    c.execute("CREATE TABLE message(id TEXT)")
    c.commit()
    r.refresh(NOW)
    assert r.status == "error" and r.snapshot(NOW) == before
    assert len(caplog.records) == 2


@pytest.mark.parametrize("kind", ["non-git", "temp", "relative"])
def test_exclusions(db, kind):
    path, c, repo = db
    cwd = {"non-git": path.parent, "temp": repo, "relative": "repo"}[kind]
    c.execute("DELETE FROM message")
    insert(c, "excluded", message(cwd))
    c.commit()
    assert reader(path, repo if kind == "temp" else None).snapshot(NOW) == []


def test_malformed_json_missing_cost_and_creation_time(db):
    path, c, repo = db
    c.execute("UPDATE message SET data='{' WHERE id='a'")
    obj = message(repo, days=1)
    del obj["cost"]
    insert(c, "missing", obj)
    c.execute("UPDATE message SET time_created=?", (int(NOW.timestamp() * 1000),))
    c.commit()
    r = reader(path)
    assert r.status == "ok"
    w = r.snapshot(NOW)[0]
    assert w["today"]["in"] == 0
    assert w["7d"]["in"] == 10 and w["7d"]["cost_partial"] is True


def test_absent_clears_previous_snapshot(db):
    path, c, _ = db
    r = reader(path)
    c.close()
    path.unlink()
    r.refresh(NOW)
    assert r.status == "absent" and r.snapshot(NOW) == []
