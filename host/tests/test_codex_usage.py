"""Codex usage contract: per-response tokens, estimated cost, incremental reads."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from clawd_tank_daemon.codex_usage import CodexUsageReader

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
MODEL = "gpt-6.1-sol"


def record(kind, **payload):
    return {"type": kind, "timestamp": "2026-10-13T08:00:00Z", "payload": payload}


def response(rid, inp=100, cr=20, cw=10, out=30, ts=None):
    # Inspected read-only on 2026-10-16: rollouts dated 2026-09-11 and 2026-10-10.
    # The older file has only token_count; the newer has token_usage_record with
    # payload.response_id and payload.usage. Input includes cached input:
    # input=17714, cached=7168, output=21, total=17735 (input + output).
    # Observed cache writes were zero: their inclusion cannot be confirmed from
    # these files. Nonzero cache-write subtraction below follows the SDD contract.
    obj = record("token_usage_record", response_id=rid, usage={
        "input_tokens": inp, "cached_input_tokens": cr, "cache_write_input_tokens": cw,
        "output_tokens": out, "reasoning_output_tokens": 12})
    if ts:
        obj["timestamp"] = ts
    return obj


def write(path, entries, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf8", newline="\n") as fh:
        for obj in entries:
            fh.write((obj if isinstance(obj, str) else json.dumps(obj)) + "\n")


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    (path / ".git").mkdir(parents=True)
    (path / "sub").mkdir()
    return path


def reader(root, temp_root=None):
    r = CodexUsageReader(root, tz=timezone.utc,
                         temp_root=str(temp_root or Path(root).parent / "fake-tmp"))
    r.refresh()
    return r


def header(cwd, model=MODEL):
    return [record("session_meta", cwd=str(cwd)), record("turn_context", model=model)]


def test_no_double_counting_and_windows(tmp_path, repo):
    root = tmp_path / "sessions"
    write(root / "2026/10/13/rollout-test.jsonl", header(repo / "sub") + [
        response("r1"), record("event_msg", type="token_count", info={
            "total_token_usage": {"input_tokens": 99999}}),
        response("r2", ts="2026-09-20T08:00:00Z"), record("token_count", input_tokens=99999)])
    r = reader(root)
    p, = r.snapshot(NOW)
    assert r.status == "ok" and r.cost_kind == "estimated"
    assert p["key"] == str(repo)
    for name in ("today", "7d", "month"):
        assert p[name] == {"in": 70, "out": 30, "cw": 10, "cr": 20,
                           "cost": 0.000467, "cost_partial": False}
    assert p["30d"] == {"in": 140, "out": 60, "cw": 20, "cr": 40,
                         "cost": 0.000934, "cost_partial": False}


def test_duplicate_response_id_once_across_files(tmp_path, repo):
    root = tmp_path / "sessions"
    for name in ("a", "b"):
        write(root / f"{name}.jsonl", header(repo) + [response("r1"), response("r1")])
    r = reader(root)
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 70


@pytest.mark.parametrize("kind", ["temp", "relative", "non-git"])
def test_excluded_cwd(tmp_path, repo, kind):
    root = tmp_path / "sessions"
    excluded = tmp_path / "scratch"
    (excluded / ".git").mkdir(parents=True)
    cwd = {"temp": excluded, "relative": "repo", "non-git": tmp_path}[kind]
    write(root / "good.jsonl", header(repo) + [response("good")])
    write(root / "bad.jsonl", header(cwd) + [response("bad")])
    assert [p["key"] for p in reader(root, excluded).snapshot(NOW)] == [str(repo)]


def test_latest_model_and_priced_unpriced_shares(tmp_path, repo):
    root = tmp_path / "sessions"
    write(root / "s.jsonl", header(repo, "unknown-model") + [
        response("r1", inp=1_000_000, cr=0, cw=0, out=0)])
    r = reader(root)
    w = r.snapshot(NOW)[0]["today"]
    assert w["cost"] is None and w["cost_partial"] is True and w["in"] == 1_000_000
    write(root / "s.jsonl", [record("turn_context", model=MODEL, cwd="relative"),
          response("r2", inp=3_000_000, cr=1_000_000, cw=1_000_000, out=1_000_000)], "a")
    r.refresh()
    w = r.snapshot(NOW)[0]["today"]
    assert w["in"] == 2_000_000 and w["cost"] == pytest.approx(14.6, abs=0.01)
    assert w["cost_partial"] is True and w["unpriced"] == ["unknown-model"]


def test_garbage_partial_append_and_per_file_context(tmp_path, repo, caplog):
    root = tmp_path / "sessions"
    path = root / "s.jsonl"
    write(path, header(repo) + [response("r1"), "{garbage", [],
          record("token_usage_record", response_id="missing-usage")])
    write(root / "other.jsonl", header("relative", "other-model"))
    line = json.dumps(response("r2"))
    with path.open("ab") as fh:
        fh.write(line[:20].encode())
    r = reader(root)
    assert r.snapshot(NOW)[0]["today"]["in"] == 70 and caplog.records
    with path.open("ab") as fh:
        fh.write((line[20:] + "\n").encode())
    r.refresh()
    w = r.snapshot(NOW)[0]["today"]
    assert w["in"] == 140 and w["cost"] == 0.000934 and not w["cost_partial"]


def test_missing_fields_and_shrunken_file_reset_context(tmp_path, repo, caplog):
    root = tmp_path / "sessions"
    path = root / "s.jsonl"
    write(path, header(repo) + [response("r1")])
    r = reader(root)
    write(path, [response("r2")])
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 70
    write(path, header(repo) + [record("token_usage_record", response_id="r3",
          usage={"input_tokens": 10})], "a")
    r.refresh()
    assert r.snapshot(NOW)[0]["today"]["in"] == 80 and caplog.records


def test_absent_including_after_good_refresh(tmp_path, repo):
    root = tmp_path / "sessions"
    r = reader(root)
    assert r.status == "absent" and r.snapshot(NOW) == []
    write(root / "s.jsonl", header(repo) + [response("r1")])
    r.refresh()
    assert r.snapshot(NOW)
    (root / "s.jsonl").unlink()
    root.rmdir()
    r.refresh()
    assert r.status == "absent" and r.snapshot(NOW) == []


def test_unreadable_skipped_and_source_unchanged(tmp_path, repo, monkeypatch, caplog):
    root = tmp_path / "sessions"
    for name in ("good", "bad"):
        write(root / f"{name}.jsonl", header(repo) + [response(name)])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*.jsonl")}
    original = CodexUsageReader._read_file

    def read_file(self, path):
        if path.name == "bad.jsonl":
            raise PermissionError("unreadable fixture")
        return original(self, path)

    monkeypatch.setattr(CodexUsageReader, "_read_file", read_file)
    assert reader(root).snapshot(NOW)[0]["today"]["in"] == 70 and caplog.records
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
