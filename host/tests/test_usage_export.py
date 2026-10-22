"""Usage file schema, failure isolation and atomic publication contract."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from clawd_tank_daemon import usage_export as export
from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_daemon.claude_usage import ClaudeUsageReader

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
KINDS = dict(claude="estimated", codex="estimated", opencode="reported", pi="reported")


def project(label, tokens, cost=0.0, partial=False):
    return {"key": f"/p/{label}", "label": label, **{
        name: {"in": tokens if name in ("30d", "month") else 0, "out": 0, "cw": 0,
               "cr": 0, "cost": cost, "cost_partial": partial}
        for name in ("today", "7d", "30d", "month")}}


def readers():
    return {name: Mock(status="ok", cost_kind=kind, snapshot=Mock(return_value=[project(name, 5)]))
            for name, kind in KINDS.items()}


def test_schema_absent_error_and_top30():
    rs = readers()
    rs["claude"].snapshot.return_value = [project(str(i), i) for i in range(40)]
    doc = export.build_document(rs, NOW)
    assert set(doc) == {"version", "generated_at", "currency", "agents"}
    assert (doc["version"], doc["currency"]) == (1, "USD")
    assert datetime.fromisoformat(doc["generated_at"]) == NOW
    assert set(doc["agents"]) == {*KINDS, "kiro"}
    assert doc["agents"]["kiro"] == {"status": "absent"}
    for name in KINDS:
        agent = doc["agents"][name]
        assert agent["status"] == "ok" and agent["cost_kind"] == KINDS[name]
        assert set(agent) == {"status", "cost_kind", "totals", "projects", "billing"}
        assert set(agent["totals"]) == {"today", "7d", "30d", "month"}
        for window in agent["totals"].values():
            assert set(window) == {"in", "out", "cw", "cr", "cost", "cost_partial"}
        assert set(agent["projects"][0]) == {"key", "label", "today", "7d", "30d", "month"}
    claude = doc["agents"]["claude"]
    assert [p["label"] for p in claude["projects"]] == [str(i) for i in range(39, 9, -1)]
    assert claude["totals"]["30d"]["in"] == sum(range(40))
    rs["codex"].status = "absent"
    assert export.build_document(rs, NOW)["agents"]["codex"] == {"status": "absent"}


def test_null_and_partial_cost_totals():
    rs = readers()
    rs["claude"].snapshot.return_value = [project("a", 1, cost=None, partial=True),
                                          project("b", 2, cost=0.5)]
    totals = export.build_document(rs, NOW)["agents"]["claude"]["totals"]["30d"]
    assert totals["cost"] == 0.5 and totals["cost_partial"] is True
    rs["claude"].snapshot.return_value.pop()
    assert export.build_document(rs, NOW)["agents"]["claude"]["totals"]["30d"]["cost"] is None


@pytest.mark.asyncio
async def test_every_pass_failure_isolation_and_replace_retry(sandbox_home, monkeypatch, caplog):
    monkeypatch.setattr("clawd_tank_daemon.daemon.datetime", Mock(now=Mock(
        side_effect=[NOW + timedelta(minutes=i) for i in range(5)])))
    d = ClawdDaemon(sim_only=True)
    rs = readers()
    d._project_usage_readers = rs
    d._project_usage_reader = rs["claude"]
    path = sandbox_home / ".clawd-tank" / "project-usage.json"
    await d._refresh_project_usage()
    first = json.loads(path.read_text())
    export.os.utime(path, (1, 1))
    mtime = path.stat().st_mtime_ns
    await d._refresh_project_usage()
    unchanged = json.loads(path.read_text())
    assert unchanged["agents"] == first["agents"]
    assert unchanged["generated_at"] > first["generated_at"] and path.stat().st_mtime_ns > mtime
    first = unchanged
    rs["opencode"].refresh.side_effect = RuntimeError("broken reader")
    rs["opencode"].snapshot.return_value = []
    with monkeypatch.context() as patch:
        patch.setattr(export.os, "replace", Mock(side_effect=PermissionError("busy")))
        await d._refresh_project_usage()
    assert json.loads(path.read_text()) == first
    assert "busy" in caplog.text and "broken reader" in caplog.text
    await d._refresh_project_usage()
    second = json.loads(path.read_text())
    assert second["generated_at"] > first["generated_at"] and path.stat().st_mtime_ns > mtime
    assert second["agents"]["opencode"] == {**first["agents"]["opencode"], "status": "error"}
    assert all(second["agents"][n]["status"] == "ok" for n in ("claude", "codex", "pi"))
    rs["opencode"].refresh.side_effect = None
    rs["opencode"].status = "error"
    await d._refresh_project_usage()
    assert json.loads(path.read_text())["agents"]["opencode"] == second["agents"]["opencode"]
    assert not list(path.parent.glob("*.tmp"))


def test_interrupted_write_keeps_old_file_and_cleans_temp(tmp_path, monkeypatch, caplog):
    path = tmp_path / "project-usage.json"
    export.write_json_atomic(path, {"old": True})

    def interrupt(obj, stream, **kwargs):
        stream.write('{"partial":')
        raise OSError("interrupted")

    monkeypatch.setattr(export.json, "dump", interrupt)
    export.write_json_atomic(path, {"new": True})
    assert json.loads(path.read_text()) == {"old": True}
    assert list(tmp_path.iterdir()) == [path]
    assert "interrupted" in caplog.text


def test_excluded_cwd_never_exported(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    root = tmp_path / "sessions"
    root.mkdir()
    row = {"cwd": str(repo), "timestamp": NOW.isoformat(), "message": {
        "role": "assistant", "model": "claude-opus-4-6", "usage": {"input_tokens": 100}}}
    (root / "a.jsonl").write_text(json.dumps(row) + "\n")
    control = ClaudeUsageReader(root, temp_root=str(tmp_path / "fake-tmp"))
    control.refresh()
    assert control.snapshot(NOW)[0]["today"]["in"] == 100
    reader = ClaudeUsageReader(root, temp_root=str(tmp_path))
    reader.refresh()
    assert export.build_document({"claude": reader}, NOW)["agents"]["claude"]["projects"] == []


def test_plan_export_billing_and_failure_retention():
    rs = readers()
    good = {"status": "ok", "billing": "plan", "plan": {"status": "ok", "limits": [
        {"id": "credits", "label": "Cycle credits", "used_pct": 34, "resets_at": None}],
        "credits": {"used": 340, "limit": 1000}}}
    plans = {"claude": good, "kiro": good}
    doc = export.build_document(rs, NOW, plans=plans)
    assert doc["version"] == 1 and set(doc["agents"]) == {*KINDS, "kiro"}
    for name, entry in doc["agents"].items():
        assert entry["billing"] == ("payg" if name in ("pi", "opencode") else "plan")
    assert set(doc["agents"]["kiro"]) == {"status", "billing", "cost_kind", "plan"}
    assert doc["agents"]["kiro"]["cost_kind"] == "none"
    failed = export.build_document(rs, NOW, doc, plans={"claude": None, "kiro": None})
    for name in ("claude", "kiro"):
        assert failed["agents"][name] == {**doc["agents"][name],
            "status": "error" if name == "kiro" else "ok", "plan": {**good["plan"], "status": "error"}}
    payg = export.build_document(rs, NOW, plans={"claude": {
        "status": "ok", "billing": "payg", "plan": {"status": "no_data"}}})
    assert payg["agents"]["claude"]["billing"] == "payg"
    assert payg["agents"]["kiro"] == {"status": "absent"}
    assert "plan" not in payg["agents"]["codex"]
    assert doc["agents"]["claude"]["plan"]["status"] == "ok"


@pytest.mark.asyncio
async def test_plan_source_isolation_off_thread_and_log_once(sandbox_home, caplog):
    import threading
    from clawd_tank_daemon.plan_usage import read_claude_plan
    d = ClawdDaemon(sim_only=True)
    rs = readers()
    d._project_usage_readers, d._project_usage_reader = rs, rs["claude"]
    main_thread = threading.get_ident()
    def source(now):
        assert threading.get_ident() != main_thread
        return read_claude_plan(sandbox_home / "missing", now)
    d._plan_sources = {"claude": source, "kiro": Mock(side_effect=RuntimeError("broken plan"))}
    for _ in range(2):
        await d._refresh_project_usage()
    doc = json.loads(d._project_usage_path.read_text())
    assert doc["agents"]["claude"]["billing"] == "payg"
    assert doc["agents"]["claude"]["plan"] == {"status": "no_data"}
    assert doc["agents"]["claude"]["totals"]["30d"]["in"] == 5
    assert doc["agents"]["kiro"]["status"] == "error"
    assert caplog.text.count("Plan usage refresh failed for kiro") == 1
