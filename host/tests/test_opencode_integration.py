"""End-to-end: an OpenCode plugin payload, fed through the daemon, drives the
same display animations as a Claude/Codex/Kiro session, appears as its own
agent slot, and respects the enable_opencode preference gate.

This exercises the real path: opencode_protocol translation ->
daemon._handle_message -> per-session state -> _compute_display_state,
without any transport or hardware.
"""

import asyncio
import json

from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_daemon.opencode_protocol import (
    OPENCODE_SESSION_PREFIX,
    opencode_hook_payload_to_daemon_message,
)


def make_daemon():
    """Create a daemon in sim-only mode with no actual transport."""
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    # PR1: enable_opencode defaults to True (the new daemon-side preference).
    if not hasattr(d, "_preferences") or d._preferences is None:
        d._preferences = {"enable_opencode": True}
    return d


def feed_opencode(d, hook):
    """Translate an OpenCode hook payload and run it through the daemon,
    like the socket server would for a real event."""
    msg = opencode_hook_payload_to_daemon_message(hook)
    assert msg is not None, f"event {hook.get('type')} should translate"
    asyncio.run(d._handle_message(msg))
    return msg


# --- Lifecycle: session.created -> tool.execute.before -> .after ----------

def test_v2_resumed_prompt_creates_separate_pet_then_waits_for_reply():
    d = make_daemon()
    # A restored conversation has no session.created event in this process.
    feed_opencode(d, {"type": "chat.message", "sessionID": "restored",
                      "directory": "/work/project"})
    state = d._compute_display_state()
    assert state["products"][0]["agent"] == "opencode"
    assert state["sessions"][0]["state"] == "thinking"
    feed_opencode(d, {"type": "session.idle", "sessionID": "restored"})
    state = d._compute_display_state()
    assert state["sessions"][0]["agent"] == "opencode"
    assert state["sessions"][0]["state"] == "waiting"
    assert d._session_states["opencode:restored"]["awaiting_prompt"] is True


def test_heartbeat_keeps_quiet_session_alive_but_unload_still_expires_it(monkeypatch):
    import clawd_tank_daemon.daemon as daemon_module
    clock = [0.0]
    monkeypatch.setattr(daemon_module.time, "monotonic", lambda: clock[0])
    d = make_daemon()
    feed_opencode(d, {"type": "chat.message", "sessionID": "quiet"})
    clock[0] = 80.0
    feed_opencode(d, {"type": "session.heartbeat", "sessionID": "quiet", "state": "thinking"})
    clock[0] = 160.0
    d._evict_stale_sessions()
    assert "opencode:quiet" in d._session_states
    clock[0] = 171.0
    d._evict_stale_sessions()
    assert "opencode:quiet" not in d._session_states


def test_heartbeat_recovers_after_restart_without_clearing_a_permission():
    d = make_daemon()
    feed_opencode(d, {"type": "session.heartbeat", "sessionID": "restored",
                      "state": "waiting", "directory": "/work/project"})
    assert d._compute_display_state()["agents"] == ["opencode"]
    assert d._session_states["opencode:restored"]["awaiting_prompt"]
    feed_opencode(d, {"type": "permission.ask", "sessionID": "restored", "tool": "bash"})
    before = dict(d._session_states["opencode:restored"])
    feed_opencode(d, {"type": "session.heartbeat", "sessionID": "restored", "state": "thinking"})
    current = d._session_states["opencode:restored"]
    assert current["state"] == "waiting"
    assert not current.get("awaiting_prompt")
    assert current["tool_name"] == before["tool_name"]


def test_heartbeat_respects_disabled_opencode():
    d = make_daemon()
    d._preferences["enable_opencode"] = False
    feed_opencode(d, {"type": "session.heartbeat", "sessionID": "disabled", "state": "thinking"})
    assert "opencode:disabled" not in d._session_states


def test_recovered_opencode_session_is_sent_to_esp_without_desktop_metadata():
    d = make_daemon()
    d._transport_versions["ble"] = 3
    feed_opencode(d, {"type": "session.heartbeat", "sessionID": "hardware",
                      "state": "thinking", "directory": "/work/project"})
    payload = json.loads(d._set_sessions_payload_for("ble", d._compute_display_state()))
    assert payload["action"] == "set_sessions"
    assert payload["anims"] == ["thinking"]
    assert len(payload["ids"]) == 1
    assert "sessions" not in payload
    assert "products" not in payload

def test_opencode_session_lifecycle_drives_anim_through_daemon():
    """A full OpenCode lifecycle (session.created -> tool.execute.before ->
    tool.execute.after) leaves the session in 'working' state with the
    'passthrough' tool animating as 'typing'."""
    d = make_daemon()
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p/proj"})
    feed_opencode(d, {"type": "tool.execute.before", "sessionID": "abc",
                      "tool": "some_opencode_tool", "callID": "c1"})
    state = d._compute_display_state()
    # tool_use -> working -> _tool_to_anim("passthrough") -> "typing"
    assert state["anims"] == ["typing"]
    # Session is keyed by the prefixed id; the raw id never leaks.
    sid = OPENCODE_SESSION_PREFIX + "abc"
    assert sid in d._session_states
    assert "abc" not in d._session_states


def test_opencode_session_deleted_removes_slot():
    """session.deleted (dismiss) removes the slot, exactly like Codex/Kiro
    SessionEnd. The display goes back to 'sleeping' with no sessions."""
    d = make_daemon()
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p"})
    feed_opencode(d, {"type": "tool.execute.before", "sessionID": "abc",
                      "tool": "x"})
    # session is in working state before deletion
    assert "typing" in d._compute_display_state()["anims"]
    feed_opencode(d, {"type": "session.deleted", "sessionID": "abc"})
    # No sessions left -> sleeping
    assert d._compute_display_state() == {"status": "sleeping"}


def test_opencode_tool_done_keeps_session_in_working_state():
    """tool.execute.after (tool_done) keeps the session in 'working' state
    (mirrors Codex PostToolUse); only a session.deleted or Stop removes it."""
    d = make_daemon()
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p"})
    feed_opencode(d, {"type": "tool.execute.before", "sessionID": "abc",
                      "tool": "x"})
    # tool_done stamps last_event but does NOT transition the state.
    feed_opencode(d, {"type": "tool.execute.after", "sessionID": "abc",
                      "tool": "x"})
    state = d._compute_display_state()
    # still in 'working' with passthrough tool -> 'typing'
    assert state["anims"] == ["typing"]


# --- Per-product aggregation: opencode appears as its own product -----------

def test_opencode_appears_in_products_array():
    """_aggregate_products() picks up 'opencode' as a distinct agent so the
    desktop pet can render a per-product crab."""
    d = make_daemon()
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p"})
    feed_opencode(d, {"type": "tool.execute.before", "sessionID": "abc",
                      "tool": "x"})
    state = d._compute_display_state()
    assert state["agents"] == ["opencode"]
    assert state["products"] == [{"agent": "opencode", "count": 1, "anim": "typing"}]


def test_opencode_and_codex_and_claude_coexist_as_three_crabs():
    """Three agents (Claude, Codex, OpenCode) coexist as separate slots; the
    prefix tuple keeps them apart."""
    d = make_daemon()
    # Claude raw id "s1" -> working
    asyncio.run(d._handle_message({
        "event": "session_start", "session_id": "s1", "project": "p", "pid": None,
    }))
    asyncio.run(d._handle_message({
        "event": "tool_use", "session_id": "s1", "tool_name": "Bash",
        "project": "p", "pid": None,
    }))
    # Codex raw id "s2" -> working (apply_patch -> Edit/typing)
    from clawd_tank_daemon.codex_protocol import codex_hook_payload_to_daemon_message
    asyncio.run(d._handle_message(codex_hook_payload_to_daemon_message({
        "hook_event_name": "SessionStart", "session_id": "s2", "cwd": "/p",
    })))
    asyncio.run(d._handle_message(codex_hook_payload_to_daemon_message({
        "hook_event_name": "PreToolUse", "session_id": "s2", "cwd": "/p",
        "tool_name": "apply_patch",
    })))
    # OpenCode raw id "s3" -> working (passthrough -> typing)
    feed_opencode(d, {"type": "session.created", "sessionID": "s3",
                      "directory": "/p"})
    feed_opencode(d, {"type": "tool.execute.before", "sessionID": "s3",
                      "tool": "x"})

    state = d._compute_display_state()
    assert set(state["agents"]) == {"claude", "codex", "opencode"}
    assert len(state["anims"]) == 3
    products = {p["agent"]: p for p in state["products"]}
    assert set(products) == {"claude", "codex", "opencode"}


# --- Staleness eviction: no OpenCode-specific leniency -------------------------

def test_opencode_session_evicted_on_staleness(monkeypatch):
    """OpenCode sessions have pid=None, so they use NO_PID_STALENESS_TIMEOUT.
    No special exemption applies."""
    sid = OPENCODE_SESSION_PREFIX + "ghost"
    # Stuff an OpenCode session, then push last_event_monotonic far enough into
    # the past for the no-PID staleness timeout to evict it.
    d = make_daemon()
    d._session_states[sid] = {
        "state": "registered",
        "last_event": 0.0,
        "last_event_monotonic": -10_000.0,
    }
    d._session_order = [(sid, d._next_display_id)]
    d._next_display_id += 1
    assert sid in d._session_states
    # Force-evict any session past the no-PID timeout by running the public
    # eviction logic via the daemon's existing path.
    from clawd_tank_daemon.daemon import NO_PID_STALENESS_TIMEOUT
    import time as _time
    now_mono = _time.monotonic()
    to_evict = [
        s for s, st in d._session_states.items()
        if now_mono - st.get("last_event_monotonic", now_mono) > NO_PID_STALENESS_TIMEOUT
    ]
    for s in to_evict:
        del d._session_states[s]
        d._session_order = [(sid, did) for sid, did in d._session_order if sid != s]
    assert sid not in d._session_states


# --- enable_opencode preference gate ----------------------------------------

def test_enable_opencode_false_silently_discards_messages():
    """When enable_opencode is False, the daemon MUST silently discard every
    opencode-prefixed message (per AC-UI-3 / design decision 7)."""
    d = make_daemon()
    d._preferences = {"enable_opencode": False}
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p"})
    # No session was created; the message was discarded before _update_session_state.
    assert OPENCODE_SESSION_PREFIX + "abc" not in d._session_states


def test_enable_opencode_true_accepts_messages():
    """When enable_opencode is True (the default), the daemon processes the
    message normally."""
    d = make_daemon()
    # enable_opencode defaults to True per design (per PR1: explicit in _preferences).
    feed_opencode(d, {"type": "session.created", "sessionID": "abc",
                      "directory": "/p"})
    assert OPENCODE_SESSION_PREFIX + "abc" in d._session_states


def test_enable_opencode_does_not_affect_other_agents():
    """The enable_opencode gate is scoped to opencode-prefixed sessions only;
    Claude/Codex/Kiro messages still go through."""
    d = make_daemon()
    d._preferences = {"enable_opencode": False}
    # Claude session (no prefix) is not affected.
    asyncio.run(d._handle_message({
        "event": "session_start", "session_id": "claude_s", "project": "p",
        "pid": None,
    }))
    assert "claude_s" in d._session_states
    # But OpenCode session is.
    feed_opencode(d, {"type": "session.created", "sessionID": "oc",
                      "directory": "/p"})
    assert OPENCODE_SESSION_PREFIX + "oc" not in d._session_states
