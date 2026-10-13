"""Tests for daemon session state tracking and display state computation."""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from clawd_tank_daemon.daemon import ClawdDaemon, LOW_BATTERY_USAGE_PCT, _tool_to_anim


def make_daemon():
    """Create a daemon in sim-only mode with no actual transport."""
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    return d


def _add_session(d, sid, state_dict, display_id=None):
    """Helper: add a session to both _session_states and _session_order."""
    d._session_states[sid] = state_dict
    if sid not in [s for s, _ in d._session_order]:
        did = display_id if display_id is not None else d._next_display_id
        d._session_order.append((sid, did))
        if display_id is None:
            d._next_display_id += 1
        else:
            d._next_display_id = max(d._next_display_id, did + 1)


def _single_display(anim, state, *, project="", tool="", subagents=0):
    """Expected v2 display state for ONE claude session.

    `sessions` is the rich per-session detail for the desktop Activity panel
    (agent, project, state, tool, subagents); the transport adapter strips it
    before it reaches hardware.
    """
    return {
        "anims": [anim],
        "ids": [1],
        "agents": ["claude"],
        "products": [{"agent": "claude", "count": 1, "anim": anim}],
        "sessions": [{
            "agent": "claude",
            "project": project,
            "state": state,
            "tool": tool,
            "subagents": subagents,
        }],
        "subagents": subagents,
    }


def test_no_sessions_returns_sleeping():
    d = make_daemon()
    assert d._compute_display_state() == {"status": "sleeping"}

def test_single_registered_session_returns_idle():
    d = make_daemon()
    _add_session(d, "s1", {"state": "registered", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("idle", "registered")

def test_single_idle_session_returns_idle():
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("idle", "idle")

def test_single_thinking_session_returns_thinking():
    d = make_daemon()
    _add_session(d, "s1", {"state": "thinking", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("thinking", "thinking")

def test_single_working_session_returns_typing():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("typing", "working")

def test_two_working_sessions_returns_two_typing():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["typing", "typing"]
    assert len(state["ids"]) == 2


# --- Per-slot agent/product (derived from the session-id prefix) ---

def test_agents_array_derives_product_from_prefix():
    """Each slot reports its product: Claude (no prefix), Codex ('codex:'),
    Kiro ('kiro:'). Aligned 1:1 with anims/ids."""
    d = make_daemon()
    _add_session(d, "s_claude", {"state": "working", "last_event": time.time()})
    _add_session(d, "codex:s_cx", {"state": "working", "last_event": time.time()})
    _add_session(d, "kiro:s_ki", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["agents"] == ["claude", "codex", "kiro"]
    assert len(state["agents"]) == len(state["anims"]) == len(state["ids"])


def test_agents_groups_kiro_ide_and_cli_as_one_product():
    """Kiro IDE and Kiro CLI both namespace with 'kiro:', so both report 'kiro'
    — the desktop pet groups them into one product window with a xN counter."""
    d = make_daemon()
    _add_session(d, "kiro:sess_ide", {"state": "working", "last_event": time.time()})
    _add_session(d, "kiro:sess_cli", {"state": "thinking", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["agents"] == ["kiro", "kiro"]

# --- Per-product aggregation (Phase 2 xN) ---

def test_products_counts_sessions_per_product():
    """products collapses sessions into one entry per product with a count."""
    d = make_daemon()
    _add_session(d, "c1", {"state": "working", "last_event": time.time()})
    _add_session(d, "c2", {"state": "working", "last_event": time.time()})
    _add_session(d, "kiro:k1", {"state": "thinking", "last_event": time.time()})
    products = d._compute_display_state()["products"]
    assert products == [
        {"agent": "claude", "count": 2, "anim": "typing"},
        {"agent": "kiro", "count": 1, "anim": "thinking"},
    ]


def test_products_order_is_first_seen():
    """Product entries keep first-seen order so the pet layout stays stable."""
    d = make_daemon()
    _add_session(d, "kiro:k1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "c1", {"state": "idle", "last_event": time.time()})
    products = d._compute_display_state()["products"]
    assert [p["agent"] for p in products] == ["kiro", "claude"]


def test_products_anim_is_most_actionable_session():
    """When one product has sessions in different states, the product crab shows
    the highest-priority one: alert > work > thinking > idle."""
    d = make_daemon()
    _add_session(d, "c1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "c2", {"state": "working", "last_event": time.time()})
    _add_session(d, "c3", {"state": "waiting", "last_event": time.time()})
    products = d._compute_display_state()["products"]
    assert products == [{"agent": "claude", "count": 3, "anim": "alert"}]


def test_products_count_includes_sessions_beyond_four_visible_slots():
    """The 4-slot cap on anims/ids does NOT cap the product count: the grouped
    view replaces individual slots, so xN must be the true total."""
    d = make_daemon()
    for i in range(6):
        _add_session(d, f"c{i}", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert len(state["anims"]) == 4          # per-slot list still capped
    assert state["overflow"] == 2
    assert state["products"] == [{"agent": "claude", "count": 6, "anim": "typing"}]


def test_three_plus_working_sessions_capped_at_four():
    d = make_daemon()
    for i in range(5):
        _add_session(d, f"s{i}", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert len(state["anims"]) == 4  # max visible
    assert state["overflow"] == 1

def test_working_and_thinking_mixed():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time()})
    _add_session(d, "s2", {"state": "thinking", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["typing", "thinking"]

def test_thinking_and_confused_mixed():
    d = make_daemon()
    _add_session(d, "s1", {"state": "thinking", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["thinking", "confused"]

def test_confused_and_idle_mixed():
    d = make_daemon()
    _add_session(d, "s1", {"state": "confused", "last_event": time.time()})
    _add_session(d, "s2", {"state": "idle", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["confused", "idle"]

def test_registered_treated_as_idle():
    d = make_daemon()
    _add_session(d, "s1", {"state": "registered", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["idle", "confused"]


# --- Task 4: _handle_message wiring ---

@pytest.mark.asyncio
async def test_session_start_registers_session():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    assert "s1" in d._session_states
    assert d._session_states["s1"]["state"] == "registered"

@pytest.mark.asyncio
async def test_prompt_submit_sets_thinking():
    d = make_daemon()
    d._session_states["s1"] = {"state": "idle", "last_event": time.time()}
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "thinking"

@pytest.mark.asyncio
async def test_tool_use_sets_working():
    d = make_daemon()
    d._session_states["s1"] = {"state": "thinking", "last_event": time.time()}
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "working"

@pytest.mark.asyncio
async def test_stop_add_sets_waiting():
    """End of turn with no running subagents rests in 'waiting' so the user sees
    the crab is waiting for their next prompt (Option B)."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._session_states["s1"]["state"] == "waiting"

@pytest.mark.asyncio
async def test_stop_add_with_subagents_stays_idle_for_conducting():
    """If subagents are still running at Stop, the turn's work isn't done — stay
    out of 'waiting' so the display shows 'conducting', not a false alert."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time(), "subagents": {"a1"}}
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._session_states["s1"]["state"] == "idle"

@pytest.mark.asyncio
async def test_idle_prompt_notification_sets_waiting():
    """Claude Code's idle_prompt ("waiting for your input") blocks on the user, so
    it surfaces the waiting alert."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "idle", "last_event": time.time()}
    await d._handle_message({
        "event": "add", "hook": "Notification", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._session_states["s1"]["state"] == "waiting"

@pytest.mark.asyncio
async def test_session_end_removes_session():
    d = make_daemon()
    d._session_states["s1"] = {"state": "idle", "last_event": time.time()}
    await d._handle_message({"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"})
    assert "s1" not in d._session_states

@pytest.mark.asyncio
async def test_implicit_session_creation():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    assert "s1" in d._session_states
    assert d._session_states["s1"]["state"] == "working"

@pytest.mark.asyncio
async def test_last_display_state_tracks_changes():
    d = make_daemon()
    assert d._last_display_state == {"status": "sleeping"}
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    assert d._last_display_state == _single_display("idle", "registered")
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    assert d._last_display_state == _single_display("thinking", "thinking")
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    assert d._last_display_state == _single_display("typing", "working")
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._last_display_state == _single_display("waiting_reply", "waiting", project="proj")
    await d._handle_message({"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"})
    assert d._last_display_state == {"status": "sleeping"}


# --- Task 5: staleness eviction and compact handling ---

def test_staleness_evicts_old_sessions():
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
    }
    d._session_staleness_timeout = 1
    d._evict_stale_sessions()
    assert "s1" not in d._session_states

def test_staleness_does_not_evict_waiting_session():
    """A 'waiting' session is blocked on the human and legitimately emits no events;
    time-based eviction would wrongly drop the alert while the user is away. The
    PID-liveness checker still evicts it if the Claude process actually dies."""
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "waiting",
        "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
    }
    d._session_staleness_timeout = 1
    d._evict_stale_sessions()
    assert "s1" in d._session_states


def test_staleness_keeps_fresh_sessions():
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
    }
    d._session_staleness_timeout = 600
    d._evict_stale_sessions()
    assert "s1" in d._session_states

@pytest.mark.asyncio
async def test_compact_triggers_sweeping():
    """V2 transport receives set_sessions with 'sweeping' for the compacting session."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time()})
    transport = AsyncMock()
    transport.is_connected = True
    d._transports["test"] = transport
    d._transport_queues["test"] = asyncio.Queue()
    d._transport_versions["test"] = 2  # v2 transport to get set_sessions
    d._last_display_state = {"anims": ["typing"], "ids": [1], "subagents": 0}

    await d._handle_message({"event": "compact", "session_id": "s1"})

    calls = transport.write_notification.call_args_list
    payloads = [json.loads(c[0][0]) for c in calls]
    # V2: single set_sessions payload with the compacting session showing "sweeping"
    session_payloads = [p for p in payloads if p.get("action") == "set_sessions"]
    assert len(session_payloads) == 1
    assert "sweeping" in session_payloads[0]["anims"]


# --- Subagent tracking ---

@pytest.mark.asyncio
async def test_subagent_start_tracks_agent_id():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    assert "a1" in d._session_states["s1"]["subagents"]

@pytest.mark.asyncio
async def test_subagent_stop_removes_agent_id():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time(), "subagents": {"a1"}}
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})
    assert "a1" not in d._session_states["s1"].get("subagents", set())

@pytest.mark.asyncio
async def test_subagent_start_creates_session_if_missing():
    d = make_daemon()
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    assert "s1" in d._session_states
    assert "a1" in d._session_states["s1"]["subagents"]

@pytest.mark.asyncio
async def test_subagent_start_refreshes_last_event():
    d = make_daemon()
    old_time = time.time() - 500
    d._session_states["s1"] = {"state": "working", "last_event": old_time}
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    assert d._session_states["s1"]["last_event"] > old_time

@pytest.mark.asyncio
async def test_subagent_stop_refreshes_last_event():
    d = make_daemon()
    old_time = time.time() - 500
    d._session_states["s1"] = {"state": "working", "last_event": old_time, "subagents": {"a1"}}
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})
    assert d._session_states["s1"]["last_event"] > old_time

@pytest.mark.asyncio
async def test_subagent_stop_for_unknown_agent_is_noop():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    # Should not crash
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "unknown"})
    assert d._session_states["s1"]["state"] == "working"

@pytest.mark.asyncio
async def test_multiple_subagents_tracked():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a2"})
    assert d._session_states["s1"]["subagents"] == {"a1", "a2"}
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})
    assert d._session_states["s1"]["subagents"] == {"a2"}


@pytest.mark.asyncio
async def test_subagent_start_with_empty_agent_id_ignored():
    """Empty agent_id must not pollute the subagents set."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "idle", "last_event": time.time()}
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": ""})
    assert not d._session_states["s1"].get("subagents")


# --- Task 4 / Task 5: eviction suppression and subagent display state ---

def test_staleness_evicts_sessions_with_dead_subagents():
    """Stale sessions are evicted even if subagents exist — stale last_event_monotonic
    means subagent tool calls stopped refreshing it, so they're dead."""
    d = make_daemon()
    d._session_staleness_timeout = 1
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
        "subagents": {"a1"},
    }
    d._evict_stale_sessions()
    assert "s1" not in d._session_states  # evicted — subagents are dead too


def test_staleness_keeps_sessions_with_active_subagents():
    """Sessions with active subagents stay alive because subagent tool calls
    refresh last_event_monotonic via PreToolUse on the parent session."""
    d = make_daemon()
    d._session_staleness_timeout = 600
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time(),  # fresh — subagent is active
        "last_event_monotonic": time.monotonic(),
        "subagents": {"a1"},
    }
    d._evict_stale_sessions()
    assert "s1" in d._session_states  # NOT evicted — still fresh


def test_idle_session_with_subagents_counts_as_conducting():
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "idle",
        "last_event": time.time(),
        "subagents": {"a1"},
    })
    state = d._compute_display_state()
    assert state["anims"] == ["conducting"]
    assert state["subagents"] == 1


def test_multiple_sessions_with_subagents():
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "idle", "last_event": time.time(), "subagents": {"a1"},
    })
    _add_session(d, "s2", {
        "state": "working", "last_event": time.time(),
    })
    state = d._compute_display_state()
    assert state["anims"] == ["conducting", "typing"]
    assert state["subagents"] == 1


def test_session_with_empty_subagents_not_counted_as_building():
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "idle",
        "last_event": time.time(),
        "subagents": set(),
    })
    state = d._compute_display_state()
    assert state["anims"] == ["idle"]
    assert state["subagents"] == 0


# --- Task 6: edge case tests and integration test ---

@pytest.mark.asyncio
async def test_session_end_clears_subagents():
    """SessionEnd removes session entirely, even with active subagents."""
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "working", "last_event": time.time(), "subagents": {"a1", "a2"},
    }
    await d._handle_message({"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"})
    assert "s1" not in d._session_states
    # Subsequent SubagentStop for orphaned agent is safe no-op
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})
    assert "s1" not in d._session_states

@pytest.mark.asyncio
async def test_duplicate_subagent_start_is_idempotent():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    assert d._session_states["s1"]["subagents"] == {"a1"}

def test_working_session_with_subagents_counts_once():
    """A working session with subagents shows its own work; the subagent is
    reported once through the HUD counter."""
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "working", "last_event": time.time(), "subagents": {"a1"},
    })
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]
    assert state["subagents"] == 1

@pytest.mark.asyncio
async def test_subagent_lifecycle():
    """Full lifecycle: subagent keeps session working while active,
    Stop doesn't clear subagents (background agents may still run),
    staleness eviction cleans up dead subagents."""
    d = make_daemon()

    # Session starts and begins working
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    assert d._compute_display_state() == _single_display("idle", "registered")

    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    assert d._compute_display_state() == _single_display("typing", "working")

    # Subagent spawned — the session keeps showing its own work
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]
    assert state["subagents"] == 1
    assert "a1" in d._session_states["s1"]["subagents"]

    # Stop fires — session state goes idle, but subagent keeps it conducting
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._session_states["s1"]["state"] == "idle"
    assert "a1" in d._session_states["s1"]["subagents"]
    state = d._compute_display_state()
    assert state["anims"] == ["conducting"]

    # Subagent finishes via SubagentStop
    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})
    assert not d._session_states["s1"].get("subagents")
    assert d._compute_display_state() == _single_display("idle", "idle", project="proj")

    # Staleness eviction works normally
    d._session_states["s1"]["last_event"] = time.time() - 9999
    d._session_states["s1"]["last_event_monotonic"] = time.monotonic() - 9999
    d._evict_stale_sessions()
    assert "s1" not in d._session_states
    assert d._compute_display_state() == {"status": "sleeping"}


@pytest.mark.asyncio
async def test_stale_subagents_evicted_with_session():
    """Missed SubagentStop hooks don't prevent eviction — if last_event_monotonic is
    stale, subagent tool calls stopped refreshing it, so they're dead."""
    d = make_daemon()
    d._session_staleness_timeout = 1
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
        "subagents": {"orphan1", "orphan2"},
    }
    d._evict_stale_sessions()
    assert "s1" not in d._session_states
    assert d._compute_display_state() == {"status": "sleeping"}


# --- Session state persistence ---


def make_daemon_with_path(sessions_path):
    """Create a test daemon that uses a custom sessions file path."""
    d = ClawdDaemon(sim_only=True, sessions_path=sessions_path)
    d._transports.clear()
    d._transport_queues.clear()
    return d


@pytest.mark.asyncio
async def test_daemon_persists_on_handle_message(tmp_path):
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    assert path.exists()
    data = json.loads(path.read_text())
    assert "s1" in data["sessions"]
    assert data["sessions"]["s1"]["state"] == "registered"


@pytest.mark.asyncio
async def test_daemon_does_not_persist_on_last_event_only_update(tmp_path):
    """tool_use when already working only updates last_event — no disk write."""
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    d._persist_sessions()  # initial save
    mtime_before = path.stat().st_mtime_ns
    import time as _time; _time.sleep(0.01)
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    mtime_after = path.stat().st_mtime_ns
    assert mtime_before == mtime_after


@pytest.mark.asyncio
async def test_daemon_persists_on_state_transition(tmp_path):
    """thinking → working is a structural change — should persist."""
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    d._session_states["s1"] = {"state": "thinking", "last_event": time.time()}
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    data = json.loads(path.read_text())
    assert data["sessions"]["s1"]["state"] == "working"


def test_daemon_persists_on_eviction(tmp_path):
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
    }
    d._session_staleness_timeout = 1
    d._evict_stale_sessions()
    data = json.loads(path.read_text())
    assert "s1" not in data["sessions"]


def test_daemon_loads_on_init(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({
        "s1": {"state": "working", "last_event": time.time()},
    }))
    d = ClawdDaemon(sim_only=True, sessions_path=path)
    d._transports.clear()
    d._transport_queues.clear()
    assert "s1" in d._session_states
    assert d._session_states["s1"]["state"] == "working"


def test_daemon_loads_subagents_as_sets(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({
        "s1": {
            "state": "idle",
            "last_event": time.time(),
            "subagents": ["a1", "a2"],
        },
    }))
    d = ClawdDaemon(sim_only=True, sessions_path=path)
    d._transports.clear()
    d._transport_queues.clear()
    assert d._session_states["s1"]["subagents"] == {"a1", "a2"}
    assert isinstance(d._session_states["s1"]["subagents"], set)


def test_daemon_startup_display_state_from_loaded_sessions(tmp_path):
    path = tmp_path / "sessions.json"
    # Use envelope format with session_order so _compute_display_state works
    path.write_text(json.dumps({
        "sessions": {
            "s1": {"state": "working", "last_event": time.time()},
        },
        "session_order": [["s1", 1]],
        "next_display_id": 2,
    }))
    d = ClawdDaemon(sim_only=True, sessions_path=path)
    d._transports.clear()
    d._transport_queues.clear()
    assert d._compute_display_state() == _single_display("typing", "working")


def test_daemon_evicts_stale_sessions_on_startup(tmp_path):
    """Stale sessions from disk are evicted immediately, not after 30s."""
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({
        "stale": {"state": "working", "last_event": time.time() - 9999},
        "fresh": {"state": "idle", "last_event": time.time()},
    }))
    d = ClawdDaemon(sim_only=True, sessions_path=path)
    d._transports.clear()
    d._transport_queues.clear()
    assert "stale" not in d._session_states
    assert "fresh" in d._session_states


@pytest.mark.asyncio
async def test_session_end_persists_removal(tmp_path):
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"})
    data = json.loads(path.read_text())
    assert "s1" not in data["sessions"]


# --- Session order tracking ---


@pytest.mark.asyncio
async def test_session_order_tracks_arrival():
    """Sessions should be tracked in arrival order with stable display IDs."""
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    await d._handle_message({"event": "session_start", "session_id": "ccc"})
    assert d._session_order == [("aaa", 1), ("bbb", 2), ("ccc", 3)]


@pytest.mark.asyncio
async def test_session_order_removes_on_end():
    """Ending a middle session shifts later ones down."""
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    await d._handle_message({"event": "session_start", "session_id": "ccc"})
    await d._handle_message({"event": "dismiss", "session_id": "bbb", "hook": "SessionEnd"})
    assert d._session_order == [("aaa", 1), ("ccc", 3)]


@pytest.mark.asyncio
async def test_session_order_display_ids_never_reuse():
    """Display IDs increment and are never reused even after removal."""
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "dismiss", "session_id": "aaa", "hook": "SessionEnd"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    assert d._session_order == [("bbb", 2)]


@pytest.mark.asyncio
async def test_session_order_created_on_tool_use_if_missing():
    """tool_use creates session in order if not already tracked."""
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    assert len(d._session_order) == 1
    assert d._session_order[0][0] == "aaa"


# --- Task 2 new tests: display state v2 dict format ---


@pytest.mark.asyncio
async def test_display_state_single_session_typing():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    state = d._compute_display_state()
    assert state == _single_display("typing", "working")


@pytest.mark.asyncio
async def test_display_state_working_with_subagents_keeps_own_anim():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    await d._handle_message({"event": "subagent_start", "session_id": "aaa", "agent_id": "sub1"})
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]
    assert state["subagents"] == 1


@pytest.mark.asyncio
async def test_display_state_preserves_arrival_order():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    # bbb is registered → idle
    state = d._compute_display_state()
    assert state["anims"] == ["typing", "idle"]
    assert state["ids"] == [1, 2]


@pytest.mark.asyncio
async def test_display_state_overflow_with_5_sessions():
    d = make_daemon()
    for i in range(5):
        sid = f"s{i}"
        await d._handle_message({"event": "session_start", "session_id": sid})
        await d._handle_message({"event": "tool_use", "session_id": sid})
    state = d._compute_display_state()
    assert len(state["anims"]) == 4  # max visible
    assert state["overflow"] == 1


def test_display_state_sleeping_when_no_sessions():
    d = make_daemon()
    state = d._compute_display_state()
    assert state == {"status": "sleeping"}


@pytest.mark.asyncio
async def test_display_state_middle_session_removed():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    await d._handle_message({"event": "tool_use", "session_id": "bbb"})
    await d._handle_message({"event": "session_start", "session_id": "ccc"})
    await d._handle_message({"event": "tool_use", "session_id": "ccc"})
    # Remove middle
    await d._handle_message({"event": "dismiss", "session_id": "bbb", "hook": "SessionEnd"})
    state = d._compute_display_state()
    assert state["anims"] == ["typing", "typing"]
    assert state["ids"] == [1, 3]  # id 2 gone, others preserved


# --- Per-transport protocol versioning ---


@pytest.mark.asyncio
async def test_v1_transport_gets_set_status():
    """V1 transport should receive legacy set_status format."""
    d = make_daemon()
    transport = AsyncMock()
    transport.is_connected = True
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    d._transport_versions["ble"] = 1

    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "tool_use", "session_id": "s1"})

    calls = transport.write_notification.call_args_list
    payloads = [json.loads(c[0][0]) for c in calls]
    # Should have received set_status (v1 format), not set_sessions
    status_payloads = [p for p in payloads if p.get("action") == "set_status"]
    assert any(p["status"].startswith("working") for p in status_payloads)
    assert not any(p.get("action") == "set_sessions" for p in payloads)


@pytest.mark.asyncio
async def test_v2_transport_gets_set_sessions():
    """V2 transport should receive set_sessions format."""
    d = make_daemon()
    transport = AsyncMock()
    transport.is_connected = True
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = 2

    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "tool_use", "session_id": "s1"})

    calls = transport.write_notification.call_args_list
    payloads = [json.loads(c[0][0]) for c in calls]
    session_payloads = [p for p in payloads if p.get("action") == "set_sessions"]
    assert len(session_payloads) > 0
    assert session_payloads[-1]["anims"] == ["typing"]


@pytest.mark.asyncio
async def test_sim_transport_auto_sets_v3():
    """Simulator transport auto-sets to v3 on connect."""
    d = make_daemon()
    d._on_transport_connect("sim")
    assert d._transport_versions.get("sim") == 3


@pytest.mark.asyncio
async def test_ble_transport_defaults_v1():
    """BLE transport defaults to v1 (no auto-set)."""
    d = make_daemon()
    d._on_transport_connect("ble")
    assert d._transport_versions.get("ble") is None  # defaults to 1 via .get(name, 1)


@pytest.mark.asyncio
async def test_ble_transport_version_read_on_connect():
    """BLE transport should read version after connecting."""
    d = make_daemon()
    transport = AsyncMock()
    transport.read_version = AsyncMock(return_value=2)
    transport.is_connected = True
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    version = await transport.read_version()
    d._transport_versions["ble"] = version
    assert d._transport_versions.get("ble") == 2


# --- Per-session sweeping (Task 6) ---


class MockTransport:
    """Minimal transport stub that captures written payloads."""

    def __init__(self, name: str = "mock"):
        self.name = name
        self.is_connected = True
        self.written: list[str] = []

    async def write_notification(self, payload: str) -> None:
        self.written.append(payload)


@pytest.mark.asyncio
async def test_compact_sends_per_session_sweeping_v2():
    """V2 transport should receive set_sessions with sweeping for the compacting session."""
    d = make_daemon()
    d._transport_versions["sim"] = 2
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    await d._handle_message({"event": "tool_use", "session_id": "bbb"})
    transport.written.clear()
    await d._handle_message({"event": "compact", "session_id": "bbb"})
    payloads = [json.loads(p) for p in transport.written]
    sweeping_payload = next((p for p in payloads if p.get("action") == "set_sessions"), None)
    assert sweeping_payload is not None
    assert sweeping_payload["anims"][1] == "sweeping"  # bbb is second
    assert sweeping_payload["anims"][0] == "typing"    # aaa unchanged


# --- Task 2: error state and dizzy display mapping ---


def test_error_state_returns_dizzy():
    d = make_daemon()
    _add_session(d, "s1", {"state": "error", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("dizzy", "error")


@pytest.mark.asyncio
async def test_stop_failure_add_sets_error():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "add", "hook": "StopFailure", "session_id": "s1",
        "project": "proj", "message": "Rate limited",
    })
    assert d._session_states["s1"]["state"] == "error"


@pytest.mark.asyncio
async def test_stop_failure_exhausted_sets_out_of_credits_low_battery():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "add", "hook": "StopFailure", "session_id": "s1",
        "project": "proj", "message": "Out of credits", "exhausted": True,
    })
    assert d._session_states["s1"]["state"] == "out_of_credits"
    assert d._compute_display_state()["anims"] == ["low_battery"]


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"event": "dismiss", "hook": "UserPromptSubmit"},
    {"event": "tool_use"},
])
async def test_out_of_credits_clears_on_new_activity(event):
    d = make_daemon()
    d._session_states["s1"] = {"state": "out_of_credits", "last_event": time.time()}
    await d._handle_message({**event, "session_id": "s1"})
    assert d._session_states["s1"]["state"] in ("thinking", "working")


def test_out_of_credits_downgrades_to_idle_on_v2():
    from clawd_tank_daemon.daemon import downgrade_display_state
    d = make_daemon()
    _add_session(d, "s1", {"state": "out_of_credits", "last_event": time.time()})
    state = d._compute_display_state()
    assert downgrade_display_state(state, 2)["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_error_state_clears_on_prompt_submit():
    d = make_daemon()
    d._session_states["s1"] = {"state": "error", "last_event": time.time()}
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_error_state_clears_on_tool_use():
    d = make_daemon()
    d._session_states["s1"] = {"state": "error", "last_event": time.time()}
    await d._handle_message({"event": "tool_use", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "working"


@pytest.mark.asyncio
async def test_error_state_removed_on_session_end():
    d = make_daemon()
    d._session_states["s1"] = {"state": "error", "last_event": time.time()}
    await d._handle_message({"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"})
    assert "s1" not in d._session_states


def test_error_state_evicted_on_staleness():
    d = make_daemon()
    d._session_staleness_timeout = 1
    d._session_states["s1"] = {
        "state": "error",
        "last_event": time.time() - 9999,
        "last_event_monotonic": time.monotonic() - 9999,
    }
    d._evict_stale_sessions()
    assert "s1" not in d._session_states


@pytest.mark.asyncio
async def test_stop_then_stop_failure_overwrites_to_error():
    """Stop then StopFailure on same session — card overwrites, state becomes error."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1",
        "project": "proj", "message": "Waiting",
    })
    assert d._session_states["s1"]["state"] == "waiting"
    await d._handle_message({
        "event": "add", "hook": "StopFailure", "session_id": "s1",
        "project": "proj", "message": "Rate limited",
    })
    assert d._session_states["s1"]["state"] == "error"


@pytest.mark.asyncio
async def test_error_and_working_mixed():
    d = make_daemon()
    _add_session(d, "s1", {"state": "error", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["dizzy", "typing"]


# --- Task 2: Tool-aware animation mapping ---


def test_working_with_bash_tool_returns_building():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    state = d._compute_display_state()
    assert state["anims"] == ["building"]


def test_working_with_read_tool_returns_debugger():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Read"})
    state = d._compute_display_state()
    assert state["anims"] == ["debugger"]


def test_working_with_grep_tool_returns_debugger():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Grep"})
    state = d._compute_display_state()
    assert state["anims"] == ["debugger"]


def test_working_with_edit_tool_returns_typing():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Edit"})
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]


def test_working_with_websearch_returns_wizard():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "WebSearch"})
    state = d._compute_display_state()
    assert state["anims"] == ["wizard"]


def test_working_with_agent_returns_conducting():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Agent"})
    state = d._compute_display_state()
    assert state["anims"] == ["conducting"]


def test_working_with_lsp_returns_beacon():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "LSP"})
    state = d._compute_display_state()
    assert state["anims"] == ["beacon"]


def test_working_with_mcp_tool_returns_beacon():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "mcp__firebase__list_projects"})
    state = d._compute_display_state()
    assert state["anims"] == ["beacon"]


def test_working_with_unknown_tool_returns_typing():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "SomeFutureTool"})
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]


def test_working_no_tool_name_returns_typing():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time()})
    state = d._compute_display_state()
    assert state["anims"] == ["typing"]


def test_tool_name_wins_over_subagents():
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "working",
        "last_event": time.time(),
        "tool_name": "Read",
        "subagents": {"agent-1"},
    })
    state = d._compute_display_state()
    assert state["anims"] == [_tool_to_anim("Read")]


# --- AskUserQuestion → "waiting" state + alert animation ---


@pytest.mark.asyncio
async def test_ask_user_question_tool_use_sets_waiting():
    """PreToolUse for AskUserQuestion is a 'blocked on the human' moment, not work."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "tool_use", "session_id": "s1", "tool_name": "AskUserQuestion",
    })
    assert d._session_states["s1"]["state"] == "waiting"


def test_waiting_session_returns_alert():
    d = make_daemon()
    _add_session(d, "s1", {"state": "waiting", "last_event": time.time()})
    assert d._compute_display_state() == _single_display("alert", "waiting")


def test_waiting_and_working_mixed():
    d = make_daemon()
    _add_session(d, "s1", {"state": "waiting", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    state = d._compute_display_state()
    assert state["anims"] == ["alert", "building"]


@pytest.mark.asyncio
async def test_tool_done_askuserquestion_clears_waiting_to_thinking():
    """PostToolUse for AskUserQuestion means the user answered — Claude resumes thinking."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "waiting", "last_event": time.time()}
    await d._handle_message({
        "event": "tool_done", "session_id": "s1", "tool_name": "AskUserQuestion",
    })
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_tool_done_for_unknown_session_does_not_create_it():
    """A PostToolUse with no prior session must not spawn a phantom session."""
    d = make_daemon()
    await d._handle_message({
        "event": "tool_done", "session_id": "ghost", "tool_name": "AskUserQuestion",
    })
    assert "ghost" not in d._session_states


@pytest.mark.asyncio
async def test_tool_done_non_askuserquestion_leaves_state():
    """tool_done for any other tool just refreshes liveness, never changes state."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time()}
    await d._handle_message({
        "event": "tool_done", "session_id": "s1", "tool_name": "Bash",
    })
    assert d._session_states["s1"]["state"] == "working"


@pytest.mark.asyncio
async def test_waiting_clears_on_next_tool_use():
    """If Claude proceeds to a real tool after asking, the alert clears to working."""
    d = make_daemon()
    d._session_states["s1"] = {"state": "waiting", "last_event": time.time()}
    await d._handle_message({
        "event": "tool_use", "session_id": "s1", "tool_name": "Edit",
    })
    assert d._session_states["s1"]["state"] == "working"


def test_waiting_outranks_subagents():
    """'needs you' is the most actionable signal, so the alert outranks the subagent
    'conducting' indicator when a session with subagents is also blocked on the human."""
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "waiting", "last_event": time.time(), "subagents": {"a1"},
    })
    state = d._compute_display_state()
    assert state["anims"] == ["alert"]


def test_thinking_with_subagents_shows_thinking():
    """While background subagents run, the main session's own activity is shown
    (the HUD counter reports the subagents); conducting is only for an idle
    session that is waiting on its subagents."""
    d = make_daemon()
    _add_session(d, "s1", {
        "state": "thinking", "last_event": time.time(), "subagents": {"a1"},
    })
    state = d._compute_display_state()
    assert state["anims"] == ["thinking"]
    assert state["subagents"] == 1


@pytest.mark.asyncio
async def test_tool_done_clearing_waiting_is_persisted(tmp_path):
    """waiting → thinking is a structural change and must hit disk."""
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    d._session_states["s1"] = {"state": "waiting", "last_event": time.time()}
    await d._handle_message({
        "event": "tool_done", "session_id": "s1", "tool_name": "AskUserQuestion",
    })
    data = json.loads(path.read_text())
    assert data["sessions"]["s1"]["state"] == "thinking"


# --- PermissionRequest → waiting/alert (blocked on the human's approval) ---


@pytest.mark.asyncio
async def test_permission_request_sets_waiting():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time(), "tool_name": "Bash"}
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    assert d._session_states["s1"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_permission_request_does_not_create_missing_session():
    """A permission/tool_failed for an unknown session must NOT resurrect it (matches
    tool_done). PreToolUse always precedes a real permission prompt."""
    d = make_daemon()
    await d._handle_message({"event": "permission", "session_id": "ghost", "tool_name": "Bash"})
    assert "ghost" not in d._session_states


@pytest.mark.asyncio
async def test_permission_waiting_clears_on_next_tool_use():
    """No 'granted' hook fires — approval is followed by the tool running, so the
    alert clears on the next tool_use."""
    d = make_daemon()
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    assert d._session_states["s1"]["state"] == "working"


@pytest.mark.asyncio
async def test_permission_waiting_transitions_to_end_of_turn_waiting_on_stop():
    """A pending permission alert is superseded by end-of-turn: the Stop replaces
    the permission 'waiting' with the end-of-turn 'waiting' (crab still awaits the
    user, now for the next prompt rather than a tool approval)."""
    d = make_daemon()
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1", "project": "p", "message": "x",
    })
    assert d._session_states["s1"]["state"] == "waiting"


# --- PostToolUseFailure → confused (a tool genuinely errored) ---


@pytest.mark.asyncio
async def test_post_tool_use_failure_sets_confused():
    d = make_daemon()
    d._session_states["s1"] = {"state": "working", "last_event": time.time(), "tool_name": "Read"}
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "Read"})
    assert d._session_states["s1"]["state"] == "confused"


@pytest.mark.asyncio
async def test_tool_failed_does_not_create_missing_session():
    """A late PostToolUseFailure after SessionEnd must not resurrect a phantom session."""
    d = make_daemon()
    await d._handle_message({"event": "tool_failed", "session_id": "ghost", "tool_name": "Read"})
    assert "ghost" not in d._session_states


@pytest.mark.asyncio
async def test_tool_failed_confused_clears_on_prompt_submit():
    d = make_daemon()
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "Read"})
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_tool_failed_does_not_create_notification_card():
    """A tool failure is a transient state change, not a persistent notification card."""
    d = make_daemon()
    d._active_notifications.clear()
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "Read"})
    assert "s1" not in d._active_notifications


# --- Web tool failure → hat_mishap (the wizard hat falls over its eyes) ---


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["WebSearch", "WebFetch"])
async def test_web_tool_failure_shows_hat_mishap(tool):
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": tool})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": tool})
    assert d._compute_display_state()["anims"] == ["hat_mishap"]


@pytest.mark.asyncio
async def test_non_web_tool_failure_stays_confused():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "Bash"})
    assert d._compute_display_state()["anims"] == ["confused"]


@pytest.mark.asyncio
async def test_idle_prompt_after_web_tool_shows_waiting_reply_not_hat_mishap():
    """An idle_prompt Notification is not a web failure, even if the last tool was
    web: it must surface the end-of-turn wait, never hat_mishap."""
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "WebFetch"})
    await d._handle_message({
        "event": "add", "hook": "Stop", "session_id": "s1", "project": "p", "message": "x",
    })
    await d._handle_message({
        "event": "add", "hook": "Notification", "session_id": "s1", "project": "p", "message": "x",
    })
    assert d._compute_display_state()["anims"] == ["waiting_reply"]


# --- Low usage headroom → low_battery instead of idle ---


def test_idle_shows_low_battery_when_session_usage_high():
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": LOW_BATTERY_USAGE_PCT, "weekly_pct": 10}
    assert d._compute_display_state()["anims"] == ["low_battery"]


def test_idle_shows_low_battery_when_weekly_usage_high():
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": None, "weekly_pct": 97}
    assert d._compute_display_state()["anims"] == ["low_battery"]


def test_idle_stays_idle_below_low_battery_threshold():
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": LOW_BATTERY_USAGE_PCT - 1, "weekly_pct": None}
    assert d._compute_display_state()["anims"] == ["idle"]


def test_idle_stays_idle_without_usage_data():
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    assert d._compute_display_state()["anims"] == ["idle"]


def test_low_battery_only_replaces_idle():
    d = make_daemon()
    _add_session(d, "s1", {"state": "thinking", "last_event": time.time()})
    _add_session(d, "s2", {"state": "idle", "last_event": time.time(), "subagents": {"a1"}})
    _add_session(d, "s3", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": 99, "weekly_pct": 99}
    assert d._compute_display_state()["anims"] == ["thinking", "conducting", "low_battery"]


def _write_usage_cache(session_pct, weekly_pct):
    from clawd_tank_daemon import daemon as daemon_mod
    with open(daemon_mod.USAGE_CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"rate_limits": {
            "five_hour": {"used_percentage": session_pct},
            "seven_day": {"used_percentage": weekly_pct},
        }}, fh)


@pytest.mark.asyncio
async def test_usage_crossing_threshold_rebroadcasts_display_state():
    d = make_daemon()
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_versions["sim"] = 3
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._last_display_state = d._compute_display_state()

    _write_usage_cache(95, 20)
    await d._broadcast_usage()

    sessions = [json.loads(p) for p in transport.written
                if json.loads(p).get("action") == "set_sessions"]
    assert sessions and sessions[-1]["anims"] == ["low_battery"]

    transport.written.clear()
    _write_usage_cache(5, 20)  # new 5h window: headroom is back
    await d._broadcast_usage()
    sessions = [json.loads(p) for p in transport.written
                if json.loads(p).get("action") == "set_sessions"]
    assert sessions and sessions[-1]["anims"] == ["idle"]


# --- Subagent finished → happy oneshot on the parent session's slot ---


@pytest.mark.asyncio
async def test_subagent_stop_sends_happy_then_real_state_v3():
    d = make_daemon()
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = 3
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    await d._handle_message({"event": "session_start", "session_id": "bbb"})
    await d._handle_message({"event": "subagent_start", "session_id": "bbb", "agent_id": "a1"})
    transport.written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "bbb", "agent_id": "a1"})

    sessions = [json.loads(p) for p in transport.written
                if json.loads(p).get("action") == "set_sessions"]
    assert len(sessions) == 2
    assert sessions[0]["anims"] == ["building", "happy"]
    # The real state follows right away so the firmware returns to it once
    # the oneshot ends (it does not interrupt a playing oneshot).
    assert sessions[1]["anims"] == ["building", "idle"]
    assert d._last_display_state["anims"] == ["building", "idle"]


@pytest.mark.asyncio
async def test_subagent_stop_skips_happy_on_v1_transport():
    d = make_daemon()
    transport = MockTransport(name="ble")
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    d._transport_versions["ble"] = 1
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    transport.written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})

    statuses = [json.loads(p)["status"] for p in transport.written
                if json.loads(p).get("action") == "set_status"]
    assert statuses == ["idle"]


@pytest.mark.asyncio
async def test_subagent_stop_for_unknown_agent_sends_no_happy():
    d = make_daemon()
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = 3
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    transport.written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "nope"})

    assert not any("happy" in p for p in transport.written)


@pytest.mark.asyncio
async def test_subagent_stop_for_hidden_session_sends_no_happy():
    """A session beyond the 4 visible slots has no crab to celebrate on."""
    d = make_daemon()
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = 3
    for sid in ("s1", "s2", "s3", "s4", "s5"):
        await d._handle_message({"event": "session_start", "session_id": sid})
    await d._handle_message({"event": "subagent_start", "session_id": "s5", "agent_id": "a1"})
    transport.written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "s5", "agent_id": "a1"})

    assert not any("happy" in p for p in transport.written)


def test_idle_session_keeps_own_anim_when_notifications_active():
    """Idle sessions keep their own animation even when notifications are present."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time(), "tool_name": "Read"})
    d._active_notifications["s1"] = {"event": "add", "session_id": "s1"}
    state = d._compute_display_state()
    assert state["anims"] == ["idle", "debugger"]


def test_idle_session_stays_idle_with_multiple_working_sessions():
    """Idle sessions stay idle regardless of working sessions and notifications."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time() - 10, "tool_name": "Read"})
    _add_session(d, "s3", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    d._active_notifications["s1"] = {"event": "add", "session_id": "s1"}
    state = d._compute_display_state()
    assert state["anims"][0] == "idle"  # s1 keeps its own idle animation


def test_idle_stays_idle_when_no_working_sessions():
    """All sessions idle — no working session to mirror, so stays idle."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "idle", "last_event": time.time()})
    d._active_notifications["s1"] = {"event": "add", "session_id": "s1"}
    state = d._compute_display_state()
    assert state["anims"] == ["idle", "idle"]


def test_idle_stays_idle_when_no_notifications():
    """No notifications — idle sessions show idle even if others are working."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    state = d._compute_display_state()
    assert state["anims"] == ["idle", "building"]


def test_single_idle_session_with_notification_stays_idle():
    """Single session idle with notification — no other working session, stays idle."""
    d = make_daemon()
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._active_notifications["s1"] = {"event": "add", "session_id": "s1"}
    state = d._compute_display_state()
    assert state["anims"] == ["idle"]


# --- PID + monotonic tracking (ghost-crab fix) ---

@pytest.mark.asyncio
async def test_session_start_stamps_pid_and_monotonic():
    d = make_daemon()
    await d._handle_message({
        "event": "session_start", "session_id": "s1", "pid": 4242,
    })
    assert d._session_states["s1"]["pid"] == 4242
    assert "last_event_monotonic" in d._session_states["s1"]
    assert isinstance(d._session_states["s1"]["last_event_monotonic"], float)


@pytest.mark.asyncio
async def test_tool_use_refreshes_pid_and_monotonic():
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "working", "last_event": 1.0,
        "pid": 1111, "last_event_monotonic": 0.0,
    }
    await d._handle_message({
        "event": "tool_use", "session_id": "s1", "tool_name": "Edit", "pid": 4242,
    })
    assert d._session_states["s1"]["pid"] == 4242
    assert d._session_states["s1"]["last_event_monotonic"] > 0.0


@pytest.mark.asyncio
async def test_message_without_pid_field_does_not_crash():
    """Backwards-compat: old notify script sends no pid; daemon must cope."""
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    assert "s1" in d._session_states
    # pid should be None (or absent) — explicit absence, not error
    assert d._session_states["s1"].get("pid") is None


def test_init_stamps_monotonic_on_loaded_sessions(tmp_path):
    """After daemon restart, loaded sessions get fresh last_event_monotonic."""
    from clawd_tank_daemon.session_store import save_sessions
    sessions_path = tmp_path / "sessions.json"
    save_sessions({"s1": {"state": "idle", "last_event": time.time()}}, sessions_path)

    from clawd_tank_daemon.daemon import ClawdDaemon
    d = ClawdDaemon(sim_only=True, sessions_path=sessions_path)
    d._transports.clear()
    d._transport_queues.clear()

    assert "s1" in d._session_states
    assert "last_event_monotonic" in d._session_states["s1"]
    assert isinstance(d._session_states["s1"]["last_event_monotonic"], float)


def test_init_prunes_wall_clock_stale_sessions(tmp_path):
    """Startup prune: sessions with wall-clock last_event older than 10min
    are removed at init (their Claude Code process is almost certainly dead)."""
    from clawd_tank_daemon.session_store import save_sessions
    sessions_path = tmp_path / "sessions.json"
    save_sessions(
        {
            "fresh": {"state": "idle", "last_event": time.time()},
            "stale": {"state": "idle", "last_event": time.time() - 3600},  # 1h ago
        },
        sessions_path,
        order=[("fresh", 1), ("stale", 2)],
        next_id=3,
    )

    from clawd_tank_daemon.daemon import ClawdDaemon
    d = ClawdDaemon(sim_only=True, sessions_path=sessions_path)
    d._transports.clear()
    d._transport_queues.clear()

    assert "fresh" in d._session_states
    assert "stale" not in d._session_states
    assert d._session_order == [("fresh", 1)]


# --- Task 7: monotonic-based staleness eviction ---


def test_staleness_uses_monotonic_not_wall_clock():
    """A session with old wall-clock last_event but fresh monotonic time
    should NOT be evicted — covers macOS sleep/wake scenario."""
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time() - 9999,            # ancient wall clock
        "last_event_monotonic": time.monotonic(),    # but fresh monotonic
    }
    d._session_staleness_timeout = 600
    d._evict_stale_sessions()
    assert "s1" in d._session_states, "monotonic-fresh session evicted incorrectly"


def test_staleness_evicts_when_monotonic_old():
    """Session with old monotonic time is evicted regardless of wall clock."""
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic() - 9999,
    }
    d._session_staleness_timeout = 1
    d._evict_stale_sessions()
    assert "s1" not in d._session_states


# --- PID-based /clear dedup (ghost-crab fix) ---

@pytest.mark.asyncio
async def test_session_start_evicts_prior_session_with_same_pid_recent():
    """SessionStart with PID that matches a recently-active session = /clear case.
    Old session is evicted in the same _handle_message call."""
    d = make_daemon()
    d._session_states["old"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),  # very recent
        "pid": 4242,
    }
    d._session_order = [("old", 1)]
    d._next_display_id = 2

    await d._handle_message({"event": "session_start", "session_id": "new", "pid": 4242})

    assert "old" not in d._session_states, "/clear dedup did not evict old session"
    assert "new" in d._session_states
    assert d._session_order == [("new", 2)], "session_order not scrubbed/updated"


@pytest.mark.asyncio
async def test_session_start_does_NOT_evict_stale_session_with_same_pid():
    """If the matching session is >60s old (monotonic), assume PID recycle, no eviction."""
    d = make_daemon()
    d._session_states["old"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic() - 120,  # 2 min old
        "pid": 4242,
    }
    d._session_order = [("old", 1)]
    d._next_display_id = 2

    await d._handle_message({"event": "session_start", "session_id": "new", "pid": 4242})

    assert "old" in d._session_states, "PID-recycle dedup wrongly evicted stale session"
    assert "new" in d._session_states


@pytest.mark.asyncio
async def test_session_start_without_pid_does_not_dedup():
    """Backwards-compat: old notify script sends no pid; dedup is skipped safely."""
    d = make_daemon()
    d._session_states["old"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
        "pid": 4242,
    }
    d._session_order = [("old", 1)]
    d._next_display_id = 2

    await d._handle_message({"event": "session_start", "session_id": "new"})  # no pid

    assert "old" in d._session_states
    assert "new" in d._session_states


@pytest.mark.asyncio
async def test_dedup_scrubs_active_notifications():
    """Evicted session's notification card is also removed."""
    d = make_daemon()
    d._session_states["old"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
        "pid": 4242,
    }
    d._active_notifications["old"] = {"event": "add", "session_id": "old"}
    d._session_order = [("old", 1)]
    d._next_display_id = 2

    await d._handle_message({"event": "session_start", "session_id": "new", "pid": 4242})

    assert "old" not in d._active_notifications


@pytest.mark.asyncio
async def test_dedup_only_fires_on_session_start():
    """A tool_use event with matching PID does NOT trigger dedup."""
    d = make_daemon()
    d._session_states["old"] = {
        "state": "idle",
        "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
        "pid": 4242,
    }
    d._session_order = [("old", 1)]
    d._next_display_id = 2

    await d._handle_message({"event": "tool_use", "session_id": "new", "pid": 4242, "tool_name": "Edit"})

    assert "old" in d._session_states
    assert "new" in d._session_states


# --- Liveness polling (ghost-crab fix) ---

def test_liveness_evicts_a_session_whose_real_process_exited(tmp_path):
    """Real child process, really killed, then probed.

    `os.kill(pid, 0)` raises nothing for a freshly-exited PID on Windows, so a
    mocked probe cannot catch a liveness check that never evicts anything.
    """
    import subprocess
    import sys

    d = ClawdDaemon(sim_only=True, sessions_path=tmp_path / "sessions.json")
    d._transports.clear()
    d._transport_queues.clear()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _add_session(d, "s1", {
            "state": "idle", "last_event": time.time(),
            "last_event_monotonic": time.monotonic(), "pid": proc.pid,
        })
        assert d._check_liveness() == []
        assert "s1" in d._session_states
    finally:
        proc.kill()
        proc.wait(timeout=30)

    assert d._check_liveness() == ["s1"]
    assert "s1" not in d._session_states
    assert d._session_order == []


def test_liveness_does_not_raise_on_a_pid_that_never_existed(tmp_path):
    """An escaping OSError kills _liveness_checker for the life of the daemon.

    Windows raises a bare OSError (WinError 87) from os.kill for an
    out-of-range PID, which the old ProcessLookupError/PermissionError handlers
    did not catch.
    """
    d = ClawdDaemon(sim_only=True, sessions_path=tmp_path / "sessions.json")
    d._transports.clear()
    d._transport_queues.clear()
    _add_session(d, "s1", {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(), "pid": 999999,
    })

    assert d._check_liveness() == ["s1"]
    assert "s1" not in d._session_states


def test_liveness_evicts_dead_pid():
    """Session whose stored PID is no longer alive is evicted."""
    from unittest.mock import patch
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(), "pid": 4242,
    }
    d._session_order = [("s1", 1)]

    with patch("clawd_tank_daemon.daemon.pid_alive", return_value=False):
        d._check_liveness()

    assert "s1" not in d._session_states
    assert d._session_order == []


def test_liveness_keeps_alive_pid():
    """Session whose PID is still alive stays."""
    from unittest.mock import patch
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(), "pid": 4242,
    }

    with patch("clawd_tank_daemon.daemon.pid_alive", return_value=True):
        d._check_liveness()

    assert "s1" in d._session_states


def test_liveness_skips_sessions_without_pid():
    """No-pid sessions (e.g. post-restart, pre-first-event) are skipped, not evicted."""
    from unittest.mock import patch
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
    }

    with patch("clawd_tank_daemon.daemon.pid_alive", return_value=False):
        d._check_liveness()

    assert "s1" in d._session_states


def test_liveness_treats_unsignalable_pid_as_alive():
    """A PID we cannot signal (another user's) counts as alive.

    The platform mapping itself lives in process_utils.pid_alive.
    """
    from unittest.mock import patch
    d = make_daemon()
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(), "pid": 4242,
    }

    with patch("clawd_tank_daemon.daemon.pid_alive", return_value=True):
        d._check_liveness()

    assert "s1" in d._session_states


def test_liveness_persists_after_eviction(tmp_path):
    """After evicting a dead session, the persisted sessions.json reflects it."""
    from unittest.mock import patch
    from clawd_tank_daemon.daemon import ClawdDaemon

    d = ClawdDaemon(sim_only=True, sessions_path=tmp_path / "sessions.json")
    d._transports.clear()
    d._transport_queues.clear()
    d._session_states["s1"] = {
        "state": "idle", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(), "pid": 4242,
    }
    d._session_order = [("s1", 1)]

    with patch("clawd_tank_daemon.daemon.pid_alive", return_value=False):
        d._check_liveness()

    # Persist file should not contain s1
    import json as _json
    raw = _json.loads((tmp_path / "sessions.json").read_text())
    assert "s1" not in raw.get("sessions", {})


# --- Stop (end of turn) → no notification card, happy oneshot instead ---


def _v3_daemon():
    d = make_daemon()
    transport = MockTransport(name="sim")
    d._transports["sim"] = transport
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = 3
    return d, transport


STOP_MSG = {"event": "add", "hook": "Stop", "session_id": "aaa",
            "project": "p", "message": "Esperando tu respuesta"}


@pytest.mark.asyncio
async def test_stop_adds_no_notification_card():
    """End of turn is not something the user must act on: no card is stored or
    forwarded to the device."""
    d, _ = _v3_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    for q in d._transport_queues.values():
        while not q.empty():
            q.get_nowait()

    await d._handle_message(dict(STOP_MSG))

    assert "aaa" not in d._active_notifications
    for q in d._transport_queues.values():
        queued = [q.get_nowait() for _ in range(q.qsize())]
        assert not any(m.get("event") == "add" for m in queued)


@pytest.mark.asyncio
async def test_stop_plays_happy_then_waiting_v3():
    """End of turn: a happy oneshot, then the crab rests in the waiting alert so
    the user sees it is awaiting their next prompt (Option B)."""
    d, transport = _v3_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    transport.written.clear()

    await d._handle_message(dict(STOP_MSG))

    sessions = [json.loads(p) for p in transport.written
                if json.loads(p).get("action") == "set_sessions"]
    assert [s["anims"] for s in sessions] == [["happy"], ["alert"]]


@pytest.mark.asyncio
async def test_stop_with_running_subagents_returns_to_conducting():
    d, transport = _v3_daemon()
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "subagent_start", "session_id": "aaa", "agent_id": "a1"})
    transport.written.clear()

    await d._handle_message(dict(STOP_MSG))

    sessions = [json.loads(p) for p in transport.written
                if json.loads(p).get("action") == "set_sessions"]
    assert [s["anims"] for s in sessions] == [["happy"], ["conducting"]]
    assert sessions[-1]["subagents"] == 1


@pytest.mark.asyncio
async def test_only_api_errors_show_a_card():
    """API errors keep their card; Claude Code's idle_prompt notification, like
    the end of a turn, shows no card."""
    d, _ = _v3_daemon()
    for q in d._transport_queues.values():
        while not q.empty():
            q.get_nowait()
    await d._handle_message({"event": "add", "hook": "StopFailure", "session_id": "aaa",
                             "project": "p", "message": "Error de API"})
    await d._handle_message({"event": "add", "hook": "Notification", "session_id": "bbb",
                             "project": "p", "message": "Claude is waiting for your input"})
    assert "aaa" in d._active_notifications
    assert "bbb" not in d._active_notifications
    for q in d._transport_queues.values():
        queued = [q.get_nowait() for _ in range(q.qsize())]
        assert [m["session_id"] for m in queued if m.get("event") == "add"] == ["aaa"]


# --- PID liveness polling cadence ---


@pytest.mark.asyncio
async def test_liveness_checker_polls_every_few_seconds():
    """A Claude Code window closed with the X sends no SessionEnd; its crab is
    removed by the PID liveness checker, so the poll interval is the delay the
    user sees. It must stay short."""
    from clawd_tank_daemon import daemon as daemon_mod

    d = make_daemon()
    d._running = True
    delays = []

    async def fake_sleep(secs):
        delays.append(secs)
        d._running = False

    with patch.object(daemon_mod.asyncio, "sleep", fake_sleep):
        await d._liveness_checker()

    assert delays == [daemon_mod.PID_LIVENESS_INTERVAL_SECS]
    assert daemon_mod.PID_LIVENESS_INTERVAL_SECS <= 5


# --- PermissionRequest wait: desk-window decision ----------------------------


import clawd_tank_daemon.daemon as daemon_mod
from clawd_tank_daemon.protocol import daemon_message_to_ble_payload


class FakeTransport:
    """Stands in for a connected transport; permission traffic goes through the
    per-transport queue, never through write_notification."""

    def __init__(self, connected=True):
        self.is_connected = connected
        self.written = []

    async def write_notification(self, payload):
        self.written.append(payload)
        return True


class FakeReply:
    """The socket server's WaitReply, minus the socket."""

    def __init__(self):
        self.sent = []
        self.disconnected = asyncio.Event()

    async def send(self, obj):
        if self.disconnected.is_set():
            return False
        self.sent.append(obj)
        return True


def make_sim_daemon(with_ble=False):
    d = make_daemon()
    d._transports["sim"] = FakeTransport()
    d._transport_queues["sim"] = asyncio.Queue()
    if with_ble:
        d._transports["ble"] = FakeTransport()
        d._transport_queues["ble"] = asyncio.Queue()
    return d


def _perm_msg(sid="s1", tool="Bash", summary="ls -la"):
    return {"event": "permission", "session_id": sid, "tool_name": tool,
            "project": "proj", "wait": True, "tool_summary": summary}


def _drain(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def _payloads(q, action=None):
    out = []
    for item in _drain(q):
        raw = daemon_message_to_ble_payload(item)
        if raw is None:
            continue
        data = json.loads(raw)
        if action is None or data.get("action") == action:
            out.append(data)
    return out


async def _start_wait(d, reply, msg=None):
    """Run _handle_message for a waiting permission and return (task, request)."""
    task = asyncio.ensure_future(d._handle_message(msg or _perm_msg(), reply))
    for _ in range(50):
        await asyncio.sleep(0)
        if d._pending_permissions:
            break
    request = None
    for p in _payloads(d._transport_queues["sim"], "permission_request"):
        request = p
    return task, request


def _decision(req, answer="allow", **override):
    ev = {"event": "permission_decision", "id": req["id"], "nonce": req["nonce"],
          "decision": answer}
    ev.update(override)
    return ev


@pytest.mark.asyncio
async def test_permission_wait_without_sim_replies_none_immediately():
    d = make_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    reply = FakeReply()
    await asyncio.wait_for(d._handle_message(_perm_msg(), reply), timeout=1)
    assert reply.sent == [{"decision": "none"}]
    assert d._session_states["s1"]["state"] == "waiting"
    assert d._pending_permissions == {}


@pytest.mark.asyncio
async def test_permission_wait_with_only_ble_or_disconnected_sim_replies_none():
    d = make_daemon()
    d._transports["ble"] = FakeTransport()
    d._transport_queues["ble"] = asyncio.Queue()
    d._transports["sim"] = FakeTransport(connected=False)
    d._transport_queues["sim"] = asyncio.Queue()
    reply = FakeReply()
    await asyncio.wait_for(d._handle_message(_perm_msg(), reply), timeout=1)
    assert reply.sent == [{"decision": "none"}]
    assert _payloads(d._transport_queues["ble"], "permission_request") == []
    assert _payloads(d._transport_queues["sim"], "permission_request") == []


@pytest.mark.asyncio
async def test_permission_without_wait_flag_keeps_old_behavior():
    d = make_sim_daemon()
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "Bash"})
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    assert d._session_states["s1"]["state"] == "waiting"
    assert d._pending_permissions == {}
    assert _payloads(d._transport_queues["sim"], "permission_request") == []


@pytest.mark.asyncio
async def test_permission_wait_enqueues_request_only_to_sim():
    d = make_sim_daemon(with_ble=True)
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    try:
        assert req is not None
        assert req["action"] == "permission_request"
        assert req["project"] == "proj" and req["tool"] == "Bash"
        assert req["summary"] == "ls -la"
        assert len(req["id"]) == 32 and len(req["nonce"]) == 16
        assert req["id"] != req["nonce"]
        # BLE got nothing permission-related, and no raw write carries the nonce.
        assert _payloads(d._transport_queues["ble"], "permission_request") == []
        assert all("permission" not in w for w in d._transports["ble"].written)
        assert all("nonce" not in w for w in d._transports["sim"].written)
        assert reply.sent == []
    finally:
        d._cancel_all_permissions()
        await task


@pytest.mark.asyncio
async def test_valid_decision_resolves_the_wait():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    d.handle_sim_event(_decision(req, "allow"))
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "allow"}]
    assert d._pending_permissions == {}


@pytest.mark.asyncio
async def test_deny_decision_resolves_as_deny():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    d.handle_sim_event(_decision(req, "deny"))
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "deny"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    {"nonce": "0" * 16},
    {"id": "f" * 32},
    {"decision": "none"},
    {"decision": "ALLOW"},
    {"decision": None},
    {"nonce": None},
    {"id": ["x"]},
])
async def test_invalid_decision_is_ignored(bad):
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    try:
        d.handle_sim_event(_decision(req, "allow", **bad))
        await asyncio.sleep(0.05)
        assert not task.done() and reply.sent == []
        assert len(d._pending_permissions) == 1
    finally:
        d._cancel_all_permissions()
        await task


@pytest.mark.asyncio
async def test_second_answer_is_ignored():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    d.handle_sim_event(_decision(req, "allow"))
    d.handle_sim_event(_decision(req, "deny"))
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "allow"}]


@pytest.mark.asyncio
async def test_two_concurrent_requests_are_routed_by_id():
    d = make_sim_daemon()
    r1, r2 = FakeReply(), FakeReply()
    t1, req1 = await _start_wait(d, r1, _perm_msg("s1"))
    t2 = asyncio.ensure_future(d._handle_message(_perm_msg("s2", summary="rm x"), r2))
    for _ in range(50):
        await asyncio.sleep(0)
        if len(d._pending_permissions) == 2:
            break
    req2 = _payloads(d._transport_queues["sim"], "permission_request")[-1]
    assert req1["id"] != req2["id"] and req2["summary"] == "rm x"
    # A decision carrying request 2's nonce but request 1's id resolves nothing.
    d.handle_sim_event(_decision(req1, "allow", nonce=req2["nonce"]))
    await asyncio.sleep(0.02)
    assert r1.sent == [] and r2.sent == []
    d.handle_sim_event(_decision(req2, "deny"))
    await asyncio.wait_for(t2, timeout=1)
    assert r2.sent == [{"decision": "deny"}] and r1.sent == []
    d.handle_sim_event(_decision(req1, "allow"))
    await asyncio.wait_for(t1, timeout=1)
    assert r1.sent == [{"decision": "allow"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_msg", [
    {"event": "tool_use", "session_id": "s1", "tool_name": "Bash"},
    {"event": "tool_done", "session_id": "s1", "tool_name": "Bash"},
    {"event": "add", "hook": "Stop", "session_id": "s1", "project": "p", "message": "x"},
    {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"},
    {"event": "dismiss", "hook": "SessionEnd", "session_id": "s1"},
])
async def test_later_activity_of_the_same_session_cancels_the_request(cleanup_msg):
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    await d._handle_message(dict(cleanup_msg))
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "none"}]
    assert d._pending_permissions == {}
    clears = _payloads(d._transport_queues["sim"], "permission_clear")
    assert clears == [{"action": "permission_clear", "id": req["id"]}]
    # A late decision for the cancelled request is dead.
    d.handle_sim_event(_decision(req, "allow"))
    assert d._pending_permissions == {}


@pytest.mark.asyncio
async def test_activity_of_another_session_does_not_cancel():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    try:
        await d._handle_message({"event": "tool_use", "session_id": "other", "tool_name": "Bash"})
        await asyncio.sleep(0.02)
        assert not task.done() and len(d._pending_permissions) == 1
    finally:
        d._cancel_all_permissions()
        await task


@pytest.mark.asyncio
async def test_hook_eof_cancels_the_request():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    reply.disconnected.set()
    await asyncio.wait_for(task, timeout=1)
    assert d._pending_permissions == {}
    assert reply.sent == []  # nobody to answer
    clears = _payloads(d._transport_queues["sim"], "permission_clear")
    assert clears == [{"action": "permission_clear", "id": req["id"]}]


@pytest.mark.asyncio
async def test_daemon_side_timeout_replies_none_and_clears(monkeypatch):
    monkeypatch.setattr(daemon_mod, "PERMISSION_DAEMON_WAIT_SECONDS", 0.05)
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "none"}]
    assert d._pending_permissions == {}
    clears = _payloads(d._transport_queues["sim"], "permission_clear")
    assert clears == [{"action": "permission_clear", "id": req["id"]}]


def test_daemon_wait_is_shorter_than_the_hook_wait():
    from clawd_tank_daemon.protocol import PERMISSION_WAIT_SECONDS
    assert PERMISSION_WAIT_SECONDS == 15
    assert daemon_mod.PERMISSION_DAEMON_WAIT_SECONDS == PERMISSION_WAIT_SECONDS - 5


@pytest.mark.asyncio
async def test_shutdown_resolves_pending_requests_as_none():
    d = make_sim_daemon()
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    d._cancel_all_permissions()
    await asyncio.wait_for(task, timeout=1)
    assert reply.sent == [{"decision": "none"}]
    assert d._pending_permissions == {}


@pytest.mark.asyncio
async def test_permission_summary_and_nonce_are_not_logged(caplog):
    import logging
    d = make_sim_daemon()
    reply = FakeReply()
    with caplog.at_level(logging.DEBUG):
        task, req = await _start_wait(d, reply, _perm_msg(summary="SECRET-COMMAND-TEXT"))
        d.handle_sim_event(_decision(req, "allow", nonce="0" * 16))
        d.handle_sim_event(_decision(req, "allow"))
        await asyncio.wait_for(task, timeout=1)
    assert "SECRET-COMMAND-TEXT" not in caplog.text
    assert req["nonce"] not in caplog.text


@pytest.mark.asyncio
async def test_sim_events_other_than_decisions_are_ignored():
    d = make_sim_daemon()
    d.handle_sim_event({"event": "window_hidden"})
    d.handle_sim_event({"event": "permission_decision"})
    d.handle_sim_event({})


@pytest.mark.asyncio
async def test_headless_sim_client_delivers_events_to_the_daemon():
    d = ClawdDaemon(sim_only=True, sim_port=19999)
    assert d._transports["sim"]._on_event_cb == d.handle_sim_event


@pytest.mark.asyncio
async def test_add_transport_chains_the_existing_event_callback():
    seen = []

    class StubSim:
        is_connected = False

        def __init__(self):
            self._on_event_cb = seen.append

        async def ensure_connected(self):
            await asyncio.sleep(3600)

        async def disconnect(self):
            pass

    d = make_daemon()
    client = StubSim()
    await d.add_transport("sim", client)
    try:
        client._on_event_cb({"event": "window_hidden"})
        assert seen == [{"event": "window_hidden"}]  # menu-bar handler still runs
        reply = FakeReply()
        d._transports["sim"] = FakeTransport()  # make the sim look connected
        task, req = await _start_wait(d, reply)
        client._on_event_cb(_decision(req, "allow"))
        await asyncio.wait_for(task, timeout=1)
        assert reply.sent == [{"decision": "allow"}]
    finally:
        d._transports["sim"] = client
        await d.remove_transport("sim")


# --- Subagent activity vs. the main agent's own work --------------------------
# Claude Code fires PreToolUse with the PARENT session_id (plus agent_id) when a
# subagent runs a tool; that must not make the main agent look like it is working.


@pytest.mark.asyncio
async def test_subagent_tool_use_does_not_overwrite_main_state():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Agent"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message(
        {"event": "tool_use", "session_id": "s1", "tool_name": "Bash", "agent_id": "a1"})
    s = d._session_states["s1"]
    assert s["state"] == "working" and s["tool_name"] == "Agent"
    assert d._compute_display_state()["anims"] == ["conducting"]


@pytest.mark.asyncio
async def test_subagent_tool_events_do_not_move_a_thinking_main_agent():
    d = make_daemon()
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    for ev in ("tool_use", "tool_done", "tool_failed"):
        await d._handle_message(
            {"event": ev, "session_id": "s1", "tool_name": "Read", "agent_id": "a1"})
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_subagent_tool_event_still_keeps_the_session_alive():
    d = make_daemon()
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    d._session_states["s1"]["last_event_monotonic"] = 0.0
    d._session_states["s1"]["last_event"] = 0.0
    await d._handle_message(
        {"event": "tool_use", "session_id": "s1", "tool_name": "Bash", "agent_id": "a1"})
    assert d._session_states["s1"]["last_event"] > 0.0
    assert d._session_states["s1"]["last_event_monotonic"] > 0.0


@pytest.mark.asyncio
async def test_main_agent_tool_use_still_sets_working():
    d = make_daemon()
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    assert d._session_states["s1"]["tool_name"] == "Bash"
    assert d._compute_display_state()["anims"] == ["building"]


@pytest.mark.asyncio
async def test_subagent_permission_still_alerts():
    """A subagent blocked on an approval needs the human, same as the main agent."""
    d = make_daemon()
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message(
        {"event": "permission", "session_id": "s1", "tool_name": "Bash", "agent_id": "a1"})
    assert d._session_states["s1"]["state"] == "waiting"


def test_products_expose_bg_when_subagents_are_running():
    d = make_daemon()
    _add_session(d, "c1", {"state": "idle", "last_event": time.time(), "subagents": {"a", "b"}})
    _add_session(d, "c2", {"state": "idle", "last_event": time.time(), "subagents": {"c"}})
    _add_session(d, "kiro:k1", {"state": "idle", "last_event": time.time()})
    products = {p["agent"]: p for p in d._compute_display_state()["products"]}
    assert products["claude"]["bg"] == 3
    assert products["claude"]["anim"] == "conducting"
    assert "bg" not in products["kiro"]


def test_products_have_no_bg_key_without_subagents():
    d = make_daemon()
    _add_session(d, "c1", {"state": "working", "tool_name": "Bash", "last_event": time.time()})
    assert d._compute_display_state()["products"] == [
        {"agent": "claude", "count": 1, "anim": "building"}]


def test_anims_for_hardware_are_unchanged_by_bg():
    d = make_daemon()
    _add_session(d, "c1", {"state": "idle", "last_event": time.time(), "subagents": {"a"}})
    state = d._compute_display_state()
    assert state["anims"] == ["conducting"] and state["subagents"] == 1


def test_products_expose_exhausted_for_out_of_credits_session():
    d = make_daemon()
    _add_session(d, "c1", {"state": "out_of_credits", "last_event": time.time()})
    _add_session(d, "kiro:k1", {"state": "idle", "last_event": time.time()})
    state = d._compute_display_state()
    products = {p["agent"]: p for p in state["products"]}
    assert products["claude"]["exhausted"] is True
    assert products["claude"]["anim"] == "low_battery"  # firmware-facing name unchanged
    assert "exhausted" not in products["kiro"]
    assert state["anims"] == ["low_battery", "idle"]


def test_exhausted_not_set_for_plain_usage_low_battery():
    d = make_daemon()
    d._latest_usage = {"session_pct": 95}
    _add_session(d, "c1", {"state": "idle", "last_event": time.time()})
    product = d._compute_display_state()["products"][0]
    assert product["anim"] == "low_battery"
    assert "exhausted" not in product


def test_exhausted_yields_to_a_sibling_session_that_is_active():
    # Another session of the same product still works / needs the user: the pet
    # shows that, the broke crab only appears when nothing more actionable exists.
    for sibling, expected in (
        ({"state": "working", "tool_name": "Bash"}, "building"),
        ({"state": "thinking"}, "thinking"),
        ({"state": "waiting"}, "alert"),
        ({"state": "idle", "subagents": {"a"}}, "conducting"),
    ):
        d = make_daemon()
        _add_session(d, "c1", {"state": "out_of_credits", "last_event": time.time()})
        _add_session(d, "c2", {**sibling, "last_event": time.time()})
        product = d._compute_display_state()["products"][0]
        assert product["anim"] == expected
        assert "exhausted" not in product, expected


def test_exhausted_wins_over_idle_siblings():
    d = make_daemon()
    _add_session(d, "c1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "c2", {"state": "out_of_credits", "last_event": time.time()})
    assert d._compute_display_state()["products"][0]["exhausted"] is True


def test_exhausted_survives_v2_downgrade_without_unknown_names():
    from clawd_tank_daemon.daemon import downgrade_display_state
    d = make_daemon()
    _add_session(d, "c1", {"state": "out_of_credits", "last_event": time.time()})
    state = d._compute_display_state()
    v2 = downgrade_display_state(state, 2)
    assert v2["anims"] == ["idle"]
    assert v2["products"][0]["exhausted"] is True


# --- "waiting" split: end-of-turn waiting_reply vs blocked alert ---
#
# A session rests in "waiting" both when its turn ended (Stop / idle_prompt:
# "your turn") and when it is blocked on the human (PermissionRequest /
# AskUserQuestion). Only the blocked kind is urgent: it keeps "alert", the
# end-of-turn kind shows "waiting_reply". Both stay state "waiting" so every
# waiting rule (eviction exemption, clears, persistence) applies to both.


def _stop(sid="s1"):
    return {"event": "add", "hook": "Stop", "session_id": sid, "project": "p", "message": "x"}


def _idle_prompt(sid="s1"):
    return {"event": "add", "hook": "Notification", "session_id": sid,
            "project": "p", "message": "Claude is waiting for your input"}


@pytest.mark.asyncio
async def test_stop_shows_waiting_reply():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(_stop())
    assert d._session_states["s1"]["state"] == "waiting"
    state = d._compute_display_state()
    assert state["anims"] == ["waiting_reply"]
    assert state["products"] == [{"agent": "claude", "count": 1, "anim": "waiting_reply"}]


@pytest.mark.asyncio
async def test_idle_prompt_shows_waiting_reply():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message(_idle_prompt())
    assert d._session_states["s1"]["state"] == "waiting"
    assert d._compute_display_state()["anims"] == ["waiting_reply"]


@pytest.mark.asyncio
async def test_permission_request_shows_alert():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    assert d._compute_display_state()["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_ask_user_question_shows_alert():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1",
                             "tool_name": "AskUserQuestion"})
    assert d._compute_display_state()["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_permission_after_end_of_turn_is_urgent_again():
    """A blocked prompt after an end-of-turn wait must not inherit waiting_reply."""
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(_stop())
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    assert d._compute_display_state()["anims"] == ["alert"]
    await d._handle_message(_stop())
    await d._handle_message({"event": "tool_use", "session_id": "s1",
                             "tool_name": "AskUserQuestion"})
    assert d._compute_display_state()["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_stop_after_permission_becomes_waiting_reply():
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(_stop())
    assert d._compute_display_state()["anims"] == ["waiting_reply"]


@pytest.mark.asyncio
async def test_stop_after_permission_is_persisted(tmp_path):
    """alert -> waiting_reply keeps state "waiting" but is still a structural
    change: the reason must reach disk, or a restart would show the wrong crab."""
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(_stop())
    d2 = make_daemon_with_path(path)
    assert d2._compute_display_state()["anims"] == ["waiting_reply"]


@pytest.mark.asyncio
@pytest.mark.parametrize("enter", [
    [_stop()],
    [_idle_prompt()],
    [{"event": "permission", "session_id": "s1", "tool_name": "Bash"}],
    [{"event": "tool_use", "session_id": "s1", "tool_name": "AskUserQuestion"}],
])
async def test_user_prompt_submit_clears_both_kinds_of_waiting(enter):
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    for msg in enter:
        await d._handle_message(msg)
    assert d._session_states["s1"]["state"] == "waiting"
    await d._handle_message({"event": "dismiss", "hook": "UserPromptSubmit", "session_id": "s1"})
    assert d._session_states["s1"]["state"] == "thinking"
    assert d._compute_display_state()["anims"] == ["thinking"]


@pytest.mark.asyncio
@pytest.mark.parametrize("enter", [_stop(), _idle_prompt()])
async def test_staleness_does_not_evict_end_of_turn_waiting(enter):
    """A PID-backed end-of-turn rest is covered by the liveness checker, never by
    the time-based eviction (a PID-less one expires, see the tests below)."""
    d = make_daemon()
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(enter)
    d._session_states["s1"]["pid"] = 4242
    d._session_states["s1"]["last_event_monotonic"] = time.monotonic() - 9999
    d._session_staleness_timeout = 1
    d._evict_stale_sessions()
    assert "s1" in d._session_states


# --- PID-less end-of-turn rest expires with the normal timeout ---
#
# Agents with no PID and no SessionEnd (Antigravity, PID-less Codex/Kiro/OpenCode)
# have no liveness checker; their end-of-turn "waiting" must still expire, with the
# normal configurable timeout (not the short no-PID one: the user is thinking).

def _rest(awaiting, idle, pid=None, **extra):
    d = make_daemon()
    s = {"state": "waiting", "last_event": time.time(),
         "last_event_monotonic": time.monotonic() - idle, **extra}
    if awaiting:
        s["awaiting_prompt"] = True
    if pid is not None:
        s["pid"] = pid
    d._session_states["s1"] = s
    d._session_staleness_timeout = 600.0
    d._evict_stale_sessions()
    return d


def test_pidless_end_of_turn_waiting_is_evicted_after_normal_timeout():
    assert "s1" not in _rest(True, 601)._session_states


def test_pidless_end_of_turn_waiting_kept_before_normal_timeout():
    # 120 s is past the 90 s no-PID timeout but the user may be thinking.
    assert "s1" in _rest(True, 120)._session_states


def test_pidless_blocked_waiting_is_never_evicted():
    assert "s1" in _rest(False, 99999)._session_states


def test_pid_backed_end_of_turn_waiting_is_not_time_evicted():
    assert "s1" in _rest(True, 99999, pid=4242)._session_states


def test_pidless_end_of_turn_waiting_with_subagents_is_not_evicted():
    assert "s1" in _rest(True, 99999, subagents={"a1"})._session_states


@pytest.mark.asyncio
async def test_pidless_end_of_turn_eviction_is_persisted_and_cleans_up(tmp_path):
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    await d._handle_message(_stop())
    d._active_notifications["s1"] = {"x": 1}
    d._session_states["s1"]["last_event_monotonic"] = time.monotonic() - 601
    d._evict_stale_sessions()
    assert "s1" not in d._session_states
    assert "s1" not in d._active_notifications
    assert d._session_order == []
    assert make_daemon_with_path(path)._session_states == {}


@pytest.mark.asyncio
async def test_stop_with_running_subagents_is_not_waiting_reply():
    d = make_daemon()
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    await d._handle_message(_stop())
    assert d._session_states["s1"]["state"] != "waiting"
    assert d._compute_display_state()["anims"] == ["conducting"]


def test_waiting_persistence_round_trip(tmp_path):
    path = tmp_path / "sessions.json"
    d = make_daemon_with_path(path)
    _add_session(d, "s1", {"state": "waiting", "last_event": time.time(),
                           "awaiting_prompt": True})
    _add_session(d, "s2", {"state": "waiting", "last_event": time.time()})
    d._persist_sessions()
    d2 = make_daemon_with_path(path)
    assert d2._compute_display_state()["anims"] == ["waiting_reply", "alert"]


def test_legacy_saved_waiting_entry_loads_as_alert(tmp_path):
    """sessions.json written before the split has a bare "waiting": it still
    loads, and shows the conservative (urgent) alert."""
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({
        "sessions": {"s1": {"state": "waiting", "last_event": time.time()}},
        "session_order": [["s1", 1]],
        "next_display_id": 2,
    }))
    d = make_daemon_with_path(path)
    assert d._session_states["s1"]["state"] == "waiting"
    assert d._compute_display_state()["anims"] == ["alert"]


def test_product_alert_outranks_waiting_reply():
    """A blocked sibling must not be masked by one that only finished its turn."""
    for order in (("reply", "blocked"), ("blocked", "reply")):
        d = make_daemon()
        for i, kind in enumerate(order):
            entry = {"state": "waiting", "last_event": time.time()}
            if kind == "reply":
                entry["awaiting_prompt"] = True
            _add_session(d, f"c{i}", entry)
        assert d._compute_display_state()["products"][0]["anim"] == "alert", order


def test_product_active_work_outranks_waiting_reply():
    """A session that finished its turn must not hide a sibling still working."""
    d = make_daemon()
    _add_session(d, "c1", {"state": "working", "tool_name": "Bash", "last_event": time.time()})
    _add_session(d, "c2", {"state": "waiting", "awaiting_prompt": True,
                           "last_event": time.time()})
    assert d._compute_display_state()["products"][0]["anim"] == "building"


# --- A blocked permission must not leave the crab stuck on "alert" ----------


def _working(d, sid="s1", tool="Bash"):
    _add_session(d, sid, {"state": "working", "tool_name": tool,
                          "last_event": time.time(), "last_event_monotonic": time.monotonic()})


@pytest.mark.asyncio
async def test_allowed_permission_leaves_alert_and_goes_back_to_working():
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    assert d._session_states["s1"]["state"] == "waiting"
    d.handle_sim_event(_decision(req, "allow"))
    await asyncio.wait_for(task, timeout=1)
    s = d._session_states["s1"]
    assert s["state"] == "working" and s["tool_name"] == "Bash"
    assert "permission_since_monotonic" not in s


@pytest.mark.asyncio
async def test_denied_permission_leaves_alert_and_goes_to_thinking():
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    d.handle_sim_event(_decision(req, "deny"))
    await asyncio.wait_for(task, timeout=1)
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_hook_hangup_means_answered_elsewhere_and_leaves_alert():
    d = make_sim_daemon()
    _working(d)
    reply = FakeReply()
    task, req = await _start_wait(d, reply)
    reply.disconnected.set()
    await asyncio.wait_for(task, timeout=1)
    assert d._session_states["s1"]["state"] == "thinking"


@pytest.mark.asyncio
async def test_daemon_timeout_keeps_the_alert_because_the_outcome_is_unknown(monkeypatch):
    # The hook falls back to the product's own prompt; the user may still be
    # deciding there, so the urgent alert stays.
    monkeypatch.setattr(daemon_mod, "PERMISSION_DAEMON_WAIT_SECONDS", 0.05)
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    await asyncio.wait_for(task, timeout=1)
    assert d._session_states["s1"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_permission_for_ask_user_question_keeps_waiting_after_allow():
    d = make_sim_daemon()
    _working(d, tool="AskUserQuestion")
    msg = _perm_msg(tool="AskUserQuestion")
    task, req = await _start_wait(d, FakeReply(), msg)
    d.handle_sim_event(_decision(req, "allow"))
    await asyncio.wait_for(task, timeout=1)
    assert d._session_states["s1"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_resolution_does_not_overwrite_newer_state():
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    # A question arrives while the permission is open: it cancels the request but
    # the session is legitimately still blocked on the human.
    await d._handle_message({"event": "tool_use", "session_id": "s1",
                             "tool_name": "AskUserQuestion"})
    await asyncio.wait_for(task, timeout=1)
    assert d._session_states["s1"]["state"] == "waiting"
    assert d._session_states["s1"]["tool_name"] == "AskUserQuestion"


@pytest.mark.asyncio
async def test_end_of_turn_rest_survives_permission_resolution():
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    await d._handle_message({"event": "add", "hook": "Stop", "session_id": "s1",
                             "project": "p", "message": "x"})
    await asyncio.wait_for(task, timeout=1)
    s = d._session_states["s1"]
    assert s["state"] == "waiting" and s.get("awaiting_prompt") is True


def _codex_permission_session(d, age):
    sid = "codex:abc"
    _add_session(d, sid, {
        "state": "waiting", "tool_name": "exec_command", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
        "permission_since_monotonic": time.monotonic() - age,
    })
    return sid


def test_codex_permission_alert_expires_after_the_bounded_window():
    d = make_daemon()
    sid = _codex_permission_session(d, daemon_mod.CODEX_PERMISSION_ALERT_SECONDS + 1)
    d._evict_stale_sessions()
    s = d._session_states[sid]
    assert s["state"] == "thinking"
    assert "permission_since_monotonic" not in s


def test_codex_permission_alert_holds_inside_the_window():
    d = make_daemon()
    sid = _codex_permission_session(d, 1)
    d._evict_stale_sessions()
    assert d._session_states[sid]["state"] == "waiting"


def test_claude_permission_alert_never_expires_by_this_rule():
    d = make_daemon()
    _add_session(d, "claude-1", {
        "state": "waiting", "tool_name": "Bash", "last_event": time.time(),
        "last_event_monotonic": time.monotonic(),
        "permission_since_monotonic": time.monotonic() - 10_000,
    })
    d._evict_stale_sessions()
    assert d._session_states["claude-1"]["state"] == "waiting"


@pytest.mark.asyncio
async def test_permission_event_stamps_when_the_block_started():
    d = make_daemon()
    _working(d)
    await d._handle_message({"event": "permission", "session_id": "s1", "tool_name": "Bash"})
    assert "permission_since_monotonic" in d._session_states["s1"]
    await d._handle_message({"event": "tool_use", "session_id": "s1", "tool_name": "Bash"})
    assert "permission_since_monotonic" not in d._session_states["s1"]


@pytest.mark.asyncio
async def test_resolving_a_permission_broadcasts_the_cleared_alert():
    d = make_sim_daemon()
    _working(d)
    task, req = await _start_wait(d, FakeReply())
    await d._broadcast_display_state_if_changed()
    assert d._last_display_state["anims"] == ["alert"]
    d.handle_sim_event(_decision(req, "allow"))
    await asyncio.wait_for(task, timeout=1)
    assert d._last_display_state["anims"] == ["building"]
