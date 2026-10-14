"""set_project_usage: pet-only transport of per-project usage (spec: project-usage-transport)."""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_daemon.protocol import project_usage_to_payload


def window(tokens=0, cost=0.0, partial=False):
    return {"in": tokens, "out": 0, "cw": 0, "cr": 0, "cost": cost, "cost_partial": partial}


def project(label, t30, **kw):
    return {"key": f"/p/{label}", "label": label, "today": window(), "7d": window(),
            "30d": window(t30, **kw), "month": window(t30)}


class FakeReader:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.refreshes = 0
        self.fail = False

    def refresh(self):
        self.refreshes += 1
        if self.fail:
            raise RuntimeError("boom")

    def snapshot(self, now):
        return self.snapshots[min(self.refreshes, len(self.snapshots)) - 1]


class MockTransport:
    def __init__(self, desktop_pet=False):
        self.desktop_pet = desktop_pet
        self.is_connected = True
        self.written = []

    async def write_notification(self, payload):
        self.written.append(payload)
        return True


def make(reader):
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    ts = {"ble": MockTransport(), "sim": MockTransport(), "pet": MockTransport(True)}
    for n, t in ts.items():
        d._transports[n] = t
        d._transport_queues[n] = asyncio.Queue()
    d._project_usage_reader = reader
    return d, ts


def usage_lines(t):
    return [json.loads(p) for p in t.written if json.loads(p).get("action") == "set_project_usage"]


# --- payload ---------------------------------------------------------------

def test_payload_shape_and_estimate_marker():
    p = json.loads(project_usage_to_payload([project("a", 5)]))
    assert p["action"] == "set_project_usage"
    assert p["currency"] == "USD" and p["estimate"] is True
    assert p["projects"][0]["label"] == "a" and p["projects"][0]["30d"]["in"] == 5


def test_payload_sorted_by_30d_tokens_and_capped_at_30_non_zero():
    snap = [project(f"p{i}", i) for i in range(0, 40)]
    projects = json.loads(project_usage_to_payload(snap))["projects"]
    assert len(projects) == 30
    assert projects[0]["label"] == "p39" and projects[-1]["label"] == "p10"


def test_payload_drops_projects_with_no_30d_or_month_usage():
    projects = json.loads(project_usage_to_payload([project("zero", 0), project("a", 1)]))["projects"]
    assert [p["label"] for p in projects] == ["a"]


def test_payload_keeps_unpriced_marker():
    snap = [project("a", 5, cost=1.0, partial=True)]
    snap[0]["30d"]["unpriced"] = ["claude-future-9"]
    out = json.loads(project_usage_to_payload(snap))["projects"][0]["30d"]
    assert out["cost_partial"] is True and out["unpriced"] == ["claude-future-9"]


# --- daemon gating ---------------------------------------------------------

@pytest.mark.asyncio
async def test_only_desktop_pet_receives_project_usage():
    d, ts = make(FakeReader([[project("a", 5)]]))
    await d._refresh_project_usage()
    assert len(usage_lines(ts["pet"])) == 1
    assert ts["ble"].written == [] and ts["sim"].written == []


@pytest.mark.asyncio
async def test_unchanged_snapshot_not_resent():
    d, ts = make(FakeReader([[project("a", 5)]]))
    await d._refresh_project_usage()
    await d._refresh_project_usage()
    assert len(usage_lines(ts["pet"])) == 1


@pytest.mark.asyncio
async def test_changed_snapshot_is_sent():
    d, ts = make(FakeReader([[project("a", 5)], [project("a", 6)]]))
    await d._refresh_project_usage()
    await d._refresh_project_usage()
    assert len(usage_lines(ts["pet"])) == 2


@pytest.mark.asyncio
async def test_pet_connect_sends_cached_snapshot_immediately():
    d, ts = make(FakeReader([[project("a", 5)]]))
    await d._refresh_project_usage()
    late = MockTransport(True)
    await d._post_connect_sync(late, "pet2")
    assert len(usage_lines(late)) == 1


@pytest.mark.asyncio
async def test_non_pet_connect_gets_no_project_usage():
    d, ts = make(FakeReader([[project("a", 5)]]))
    await d._refresh_project_usage()
    ble2 = MockTransport(False)
    await d._post_connect_sync(ble2, "ble2")
    assert usage_lines(ble2) == []


@pytest.mark.asyncio
async def test_reader_failure_is_logged_and_does_not_block_set_usage(caplog, monkeypatch):
    reader = FakeReader([[project("a", 5)]])
    reader.fail = True
    d, ts = make(reader)
    with caplog.at_level("ERROR"):
        await d._refresh_project_usage()  # must not raise
    assert "project usage" in caplog.text.lower()
    monkeypatch.setattr("clawd_tank_daemon.daemon.read_usage_from_cache",
                        lambda p: {"session_pct": 1, "weekly_pct": 2, "reset_seconds": 60})
    await d._broadcast_usage()
    assert any('"set_usage"' in p for p in ts["ble"].written)
