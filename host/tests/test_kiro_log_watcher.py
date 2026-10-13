"""Tests for the Kiro log watcher: line parsing, file tailing, daemon wiring."""

import asyncio
import json
import os
import time

import pytest

from clawd_tank_daemon.daemon import ClawdDaemon, NO_PID_STALENESS_TIMEOUT
from clawd_tank_daemon.kiro_log_watcher import (
    KiroLogTailer,
    parse_kiro_log_line,
    run_kiro_log_watcher,
)

SID = "sess_38d48c71-b963-4953-a075-8bd5bf1d2afe"

SESSION_NEW_LINE = (
    '{"timestamp":"2026-10-11T23:30:40.532Z","level":"info","message":'
    '"session.new.total {\\"sessionId\\":\\"' + SID + '\\",\\"outcome\\":'
    '\\"resolved\\",\\"durationMs\\":1823}"}'
)
USAGE_LIMIT_LINE = (
    '{"timestamp":"2026-10-11T23:31:52.492Z","level":"error","message":'
    '"UsageLimitReachedError: Usage limit reached","conversationId":"' + SID + '",'
    '"rootConversationId":"' + SID + '","turnId":"t1","rootTurnId":"t1"}'
)
TITLE_MODEL_LINE = (
    '{"timestamp":"2026-10-11T23:31:52.400Z","level":"warn","message":'
    '"llm.invokeTitleModel.error {\\"errorType\\":\\"UsageLimitReachedError\\"}",'
    '"conversationId":"' + SID + '"}'
)


# --- parse_kiro_log_line ------------------------------------------------------

def test_parse_session_new_line():
    assert parse_kiro_log_line(SESSION_NEW_LINE) == {
        "event": "session_start",
        "session_id": "kiro:" + SID,
        "project": "Kiro",
        "pid": None,
        "from_log": True,
    }


def test_parse_usage_limit_line():
    assert parse_kiro_log_line(USAGE_LIMIT_LINE) == {
        "event": "add",
        "hook": "StopFailure",
        "session_id": "kiro:" + SID,
        "project": "Kiro",
        "message": "Usage limit reached",
        "pid": None,
        "exhausted": True,
        "from_log": True,
    }


def test_parse_ignores_title_model_warning():
    assert parse_kiro_log_line(TITLE_MODEL_LINE) is None


@pytest.mark.parametrize("line", [
    "",
    "not json at all",
    "[1, 2, 3]",
    '{"level":"info","message":"something.else {}"}',
    '{"level":"info","message":"session.new.total not-json"}',
    '{"level":"info","message":"session.new.total {\\"outcome\\":\\"resolved\\"}"}',
    '{"level":"error","message":"UsageLimitReachedError: Usage limit reached"}',
    '{"level":"info","message":42}',
])
def test_parse_ignores_garbage(line):
    assert parse_kiro_log_line(line) is None


def test_parse_ignores_failed_session_new():
    line = SESSION_NEW_LINE.replace("resolved", "rejected")
    assert parse_kiro_log_line(line) is None


# --- KiroLogTailer ------------------------------------------------------------

def _log(base, folder):
    d = base / folder
    d.mkdir(parents=True, exist_ok=True)
    return d / "kiro.log"


def _append(path, text):
    with open(path, "ab") as f:
        f.write(text.encode("utf-8"))


def test_tailer_missing_base_dir_is_noop(tmp_path):
    tailer = KiroLogTailer(tmp_path / "nope")
    assert tailer.poll() == []
    assert tailer.poll() == []


def test_tailer_starts_preexisting_file_at_eof(tmp_path):
    log = _log(tmp_path, "20261011T233038417")
    _append(log, SESSION_NEW_LINE + "\n")
    tailer = KiroLogTailer(tmp_path)
    assert tailer.poll() == []  # history is not replayed
    _append(log, USAGE_LIMIT_LINE + "\n")
    msgs = tailer.poll()
    assert [m["event"] for m in msgs] == ["add"]


def test_tailer_reads_new_folder_from_start(tmp_path):
    tailer = KiroLogTailer(tmp_path)
    assert tailer.poll() == []
    log = _log(tmp_path, "20261011T233038417")
    _append(log, SESSION_NEW_LINE + "\n" + USAGE_LIMIT_LINE + "\n")
    msgs = tailer.poll()
    assert [m["event"] for m in msgs] == ["session_start", "add"]
    assert tailer.poll() == []


def test_tailer_waits_for_partial_line(tmp_path):
    tailer = KiroLogTailer(tmp_path)
    tailer.poll()
    log = _log(tmp_path, "20261011T233038417")
    half = len(SESSION_NEW_LINE) // 2
    _append(log, SESSION_NEW_LINE[:half])
    assert tailer.poll() == []
    _append(log, SESSION_NEW_LINE[half:] + "\r\n")
    msgs = tailer.poll()
    assert [m["event"] for m in msgs] == ["session_start"]


def test_tailer_resets_on_truncation(tmp_path):
    log = _log(tmp_path, "20261011T233038417")
    _append(log, ("x" * 50 + "\n") * 20)
    tailer = KiroLogTailer(tmp_path)
    tailer.poll()
    log.write_bytes((USAGE_LIMIT_LINE + "\n").encode("utf-8"))  # shorter than before
    msgs = tailer.poll()
    assert [m["event"] for m in msgs] == ["add"]


def test_tailer_tolerates_invalid_utf8(tmp_path):
    tailer = KiroLogTailer(tmp_path)
    tailer.poll()
    log = _log(tmp_path, "20261011T233038417")
    with open(log, "ab") as f:
        f.write(b"\xff\xfe garbage\n" + (SESSION_NEW_LINE + "\n").encode("utf-8"))
    msgs = tailer.poll()
    assert [m["event"] for m in msgs] == ["session_start"]


def test_tailer_follows_several_live_logs(tmp_path):
    ide = _log(tmp_path, "20261011T200000000")
    _append(ide, "")
    tailer = KiroLogTailer(tmp_path)
    tailer.poll()
    cli = _log(tmp_path, "20261011T233038417")
    _append(cli, SESSION_NEW_LINE + "\n")
    _append(ide, USAGE_LIMIT_LINE + "\n")
    events = sorted(m["event"] for m in tailer.poll())
    assert events == ["add", "session_start"]


def test_tailer_skips_old_logs(tmp_path):
    tailer = KiroLogTailer(tmp_path)
    tailer.poll()
    log = _log(tmp_path, "20250101T000000000")
    _append(log, SESSION_NEW_LINE + "\n")
    old = time.time() - 3 * 24 * 3600
    os.utime(log, (old, old))
    assert tailer.poll() == []


@pytest.mark.asyncio
async def test_run_watcher_feeds_handler_and_survives_errors(tmp_path):
    received = []
    calls = {"n": 0}

    async def handler(msg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")  # must not kill the loop
        received.append(msg)

    task = asyncio.create_task(run_kiro_log_watcher(handler, tmp_path, interval=0.01))
    await asyncio.sleep(0.05)
    log = _log(tmp_path, "20261011T233038417")
    _append(log, SESSION_NEW_LINE + "\n" + USAGE_LIMIT_LINE + "\n")
    for _ in range(100):
        if received:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [m["event"] for m in received] == ["add"]


# --- Daemon integration -------------------------------------------------------

def make_daemon():
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    return d


@pytest.mark.asyncio
async def test_daemon_session_new_shows_idle_kiro_crab():
    d = make_daemon()
    await d._handle_message(parse_kiro_log_line(SESSION_NEW_LINE))
    sid = "kiro:" + SID
    assert d._session_states[sid]["state"] == "registered"
    state = d._compute_display_state()
    assert state["anims"] == ["idle"]
    assert state["agents"] == ["kiro"]


@pytest.mark.asyncio
async def test_daemon_session_new_does_not_reset_existing_session():
    d = make_daemon()
    sid = "kiro:" + SID
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": sid})
    await d._handle_message(parse_kiro_log_line(SESSION_NEW_LINE))
    assert d._session_states[sid]["state"] == "thinking"


@pytest.mark.asyncio
async def test_daemon_usage_limit_sets_out_of_credits():
    d = make_daemon()
    sid = "kiro:" + SID
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": sid})
    await d._handle_message(parse_kiro_log_line(USAGE_LIMIT_LINE))
    assert d._session_states[sid]["state"] == "out_of_credits"
    state = d._compute_display_state()
    assert state["anims"] == ["low_battery"]
    assert state["products"][0]["exhausted"] is True
    assert d._active_notifications[sid]["message"] == "Usage limit reached"


@pytest.mark.asyncio
async def test_daemon_usage_limit_creates_unknown_session():
    d = make_daemon()
    await d._handle_message(parse_kiro_log_line(USAGE_LIMIT_LINE))
    assert d._session_states["kiro:" + SID]["state"] == "out_of_credits"


@pytest.mark.asyncio
@pytest.mark.parametrize("line", [SESSION_NEW_LINE, USAGE_LIMIT_LINE])
async def test_log_session_survives_no_pid_timeout(line):
    d = make_daemon()
    await d._handle_message(parse_kiro_log_line(line))
    sid = "kiro:" + SID
    d._session_states[sid]["last_event_monotonic"] = time.monotonic() - (NO_PID_STALENESS_TIMEOUT + 30)
    d._evict_stale_sessions()
    assert sid in d._session_states
    # ...but the normal staleness timeout still applies.
    d._session_states[sid]["last_event_monotonic"] = time.monotonic() - (d._session_staleness_timeout + 30)
    d._evict_stale_sessions()
    assert sid not in d._session_states


@pytest.mark.asyncio
async def test_log_session_uses_no_pid_timeout_once_active():
    d = make_daemon()
    await d._handle_message(parse_kiro_log_line(SESSION_NEW_LINE))
    sid = "kiro:" + SID
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": sid})
    d._session_states[sid]["last_event_monotonic"] = time.monotonic() - (NO_PID_STALENESS_TIMEOUT + 30)
    d._evict_stale_sessions()
    assert sid not in d._session_states


@pytest.mark.asyncio
async def test_hook_session_without_log_keeps_no_pid_timeout():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "kiro:x", "pid": None})
    d._session_states["kiro:x"]["last_event_monotonic"] = time.monotonic() - (NO_PID_STALENESS_TIMEOUT + 30)
    d._evict_stale_sessions()
    assert "kiro:x" not in d._session_states


@pytest.mark.asyncio
async def test_daemon_runs_and_cancels_kiro_watcher(tmp_path, monkeypatch):
    import clawd_tank_daemon.daemon as daemon_mod
    started = asyncio.Event()

    async def fake_watcher(handler, base_dir=None, interval=1.0):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(daemon_mod, "run_kiro_log_watcher", fake_watcher)
    d = make_daemon()
    run = asyncio.create_task(d.run())
    await asyncio.wait_for(started.wait(), 5)
    task = d._kiro_log_task
    await d._shutdown()
    await asyncio.wait_for(run, 5)
    assert task.cancelled()
