"""Pi usage reader: reported cost and incremental per-project aggregation."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from clawd_tank_daemon.pi_usage import PiUsageReader

UTC = timezone.utc
NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def entry(mid, ts="2026-10-13T08:00:00Z", inp=10, out=20, cw=30, cr=40, cost=0.25):
    # Real v3 records use epoch milliseconds inside message and ISO time on entry.
    return {"type": "message", "id": mid, "timestamp": ts, "message": {
        "role": "assistant", "model": "MiniMax-M2.7",
        "timestamp": int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000),
        "usage": {"input": inp, "output": out, "cacheWrite": cw, "cacheRead": cr,
                  "cost": {"total": cost}},
    }}


def session(cwd):
    return {"type": "session", "version": 3, "cwd": str(cwd)}


def write(path: Path, entries, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf8", newline="\n") as f:
        for e in entries:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "work" / "repo"
    (r / ".git").mkdir(parents=True)
    (r / "a").mkdir()
    return r


def reader(root):
    r = PiUsageReader(root, tz=UTC, temp_root=str(Path(root).parent / "fake-tmp"))
    r.refresh()
    return r


def test_fixture_totals_per_project_and_window(tmp_path, repo):
    root = tmp_path / "sessions"
    user = entry("user", inp=999, cost=99)
    user["message"]["role"] = "user"
    write(root / "encoded-directory" / "s.jsonl", [session(repo / "a"), entry("m1"),
          entry("m2", "2026-09-20T08:00:00Z", 1, 2, 3, 4, 0.5), user])
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    write(root / "other" / "s.jsonl", [session(other), entry("m3", "2026-10-01T08:00:00Z")])
    r = reader(root)
    snap = {p["label"]: p for p in r.snapshot(NOW)}
    assert r.status == "ok" and r.cost_kind == "reported"
    assert set(snap) == {"repo", "other"}
    assert snap["repo"]["key"] == str(repo)
    recent = {"in": 10, "out": 20, "cw": 30, "cr": 40, "cost": 0.25, "cost_partial": False}
    for window in ("today", "7d", "month"):
        assert snap["repo"][window] == recent
    assert snap["repo"]["30d"] == {**recent, "in": 11, "out": 22, "cw": 33, "cr": 44, "cost": 0.75}
    empty = dict.fromkeys(("in", "out", "cw", "cr"), 0) | {"cost": 0.0, "cost_partial": False}
    for window in ("today", "7d"):
        assert snap["other"][window] == empty
    for window in ("30d", "month"):
        assert snap["other"][window] == recent


def test_message_timestamp_controls_day(tmp_path, repo):
    e = entry("m1")
    e["timestamp"] = "2026-09-20T08:00:00Z"
    write(tmp_path / "sessions" / "s.jsonl", [session(repo), e])
    assert reader(tmp_path / "sessions").snapshot(NOW)[0]["today"]["in"] == 10


def test_missing_cost_and_token_fields(tmp_path, repo):
    e = entry("m1")
    del e["message"]["usage"]["cost"]
    del e["message"]["usage"]["cacheRead"]
    root = tmp_path / "sessions"
    write(root / "s.jsonl", [session(repo), e])
    w = reader(root).snapshot(NOW)[0]["today"]
    assert w == {"in": 10, "out": 20, "cw": 30, "cr": 0, "cost": 0.0, "cost_partial": True}
    write(root / "s.jsonl", [entry("m2")], mode="a")
    w = reader(root).snapshot(NOW)[0]["today"]
    assert w["cost"] == 0.25 and w["cost_partial"] is True


def test_duplicate_entry_id_counted_once(tmp_path, repo):
    root = tmp_path / "sessions"
    e = entry("m1")
    write(root / "s1.jsonl", [session(repo), e, e])
    write(root / "s2.jsonl", [session(repo), e])
    r = reader(root)
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 10
    assert r.snapshot(NOW)[0]["today"]["cost"] == 0.25


def test_garbage_and_partial_line_then_append(tmp_path, repo, caplog):
    root = tmp_path / "sessions"
    f = root / "s.jsonl"
    write(f, [session(repo), "{garbage", entry("m1")])
    line = json.dumps(entry("m2"))
    with open(f, "ab") as fh:
        fh.write(line[:20].encode())
    r = reader(root)
    assert r.snapshot(NOW)[0]["today"]["in"] == 10
    assert caplog.records
    with open(f, "ab") as fh:
        fh.write((line[20:] + "\n").encode())
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 20
    assert r.snapshot(NOW)[0]["today"]["cost"] == 0.5


def test_shrunken_file_resets_session_context(tmp_path, repo):
    root = tmp_path / "sessions"
    f = root / "s.jsonl"
    write(f, [session(repo), entry("m1"), entry("m2")])
    r = reader(root)
    write(f, [entry("m3")])
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 20
    write(f, [session(repo), entry("m4")], mode="a")
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 30


def test_missing_session_record_skipped(tmp_path, caplog):
    root = tmp_path / "sessions"
    write(root / "s.jsonl", [entry("m1")])
    assert reader(root).snapshot(NOW) == []
    assert caplog.records


def test_absent_root(tmp_path):
    r = reader(tmp_path / "absent")
    assert r.status == "absent" and r.snapshot(NOW) == []


def test_root_removed_clears_tokens_and_costs(tmp_path, repo):
    root = tmp_path / "sessions"
    path = root / "s.jsonl"
    write(path, [session(repo), entry("m1")])
    r = reader(root)
    assert r.snapshot(NOW)[0]["today"]["cost"] == 0.25
    path.unlink()
    root.rmdir()
    r.refresh()
    assert r.status == "absent" and r.snapshot(NOW) == []
    write(path, [session(repo), entry("m1", cost=0.1)])
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["cost"] == 0.1


def test_reported_cost_rounded_to_six_decimals(tmp_path, repo):
    root = tmp_path / "sessions"
    write(root / "s.jsonl", [session(repo), entry("m1", cost=0.1), entry("m2", cost=0.2)])
    assert reader(root).snapshot(NOW)[0]["today"]["cost"] == 0.3


def test_missing_ids_and_malformed_records(tmp_path, repo, caplog):
    root = tmp_path / "sessions"
    e = entry("unused", cost=0)
    del e["id"]
    write(root / "s.jsonl", [session(repo), [], {"type": "message", "message": None}, e, e])
    r = reader(root)
    r.refresh()
    assert r.snapshot(NOW)[0]["today"] == {
        "in": 20, "out": 40, "cw": 60, "cr": 80, "cost": 0.0, "cost_partial": False}
    assert caplog.records


@pytest.mark.parametrize("kind", ["non-git", "temp", "relative"])
def test_excluded_sessions(tmp_path, repo, kind):
    cwd = {"non-git": tmp_path / "scratch", "temp": repo, "relative": "work/repo"}[kind]
    root = tmp_path / "sessions"
    write(root / "s.jsonl", [session(cwd), entry("m1")])
    r = PiUsageReader(root, tz=UTC, temp_root=str(tmp_path / ("work" if kind == "temp" else "fake-tmp")))
    r.refresh()
    assert r.snapshot(NOW) == []


def test_unreadable_file_skipped_and_tree_unchanged(tmp_path, repo, monkeypatch, caplog):
    root = tmp_path / "sessions"
    write(root / "good.jsonl", [session(repo), entry("m1")])
    write(root / "bad.jsonl", [session(repo), entry("m2")])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*.jsonl")}
    original = PiUsageReader._read_file

    def read_file(self, path):
        if path.name == "bad.jsonl":
            raise PermissionError("unreadable fixture")
        return original(self, path)

    monkeypatch.setattr(PiUsageReader, "_read_file", read_file)
    r = reader(root)
    assert r.snapshot(NOW)[0]["today"]["in"] == 10
    assert caplog.records
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
