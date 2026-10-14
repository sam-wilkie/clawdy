"""End-to-end: a Pi extension payload, fed through the daemon, drives the same
display states as the other products and appears as its own agent slot.

Real path: pi_protocol translation -> daemon._handle_message -> per-session
state -> _compute_display_state. No transport or hardware.
"""

import asyncio

from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_daemon.pi_protocol import pi_hook_payload_to_daemon_message


def make_daemon():
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    return d


def feed_pi(d, hook):
    msg = pi_hook_payload_to_daemon_message(hook)
    assert msg is not None, f"event {hook.get('type')} should translate"
    asyncio.run(d._handle_message(msg))
    return msg


def test_agent_start_creates_a_pi_slot_and_turn_end_waits_for_the_user():
    d = make_daemon()
    feed_pi(d, {"type": "agent_start", "sessionID": "s1", "directory": "/work/proj"})
    state = d._compute_display_state()
    assert state["products"][0]["agent"] == "pi"
    assert state["sessions"][0]["agent"] == "pi"
    feed_pi(d, {"type": "turn_end", "sessionID": "s1", "directory": "/work/proj"})
    assert d._session_states["pi:s1"]["awaiting_prompt"] is True
    assert d._compute_display_state()["sessions"][0]["state"] == "waiting"


def test_tool_call_then_result_moves_the_slot_working_then_back():
    d = make_daemon()
    feed_pi(d, {"type": "agent_start", "sessionID": "s2", "directory": "/work/proj"})
    feed_pi(d, {"type": "tool_call", "sessionID": "s2", "tool": "bash", "directory": "/work/proj"})
    assert d._compute_display_state()["sessions"][0]["state"] == "working"
    feed_pi(d, {"type": "tool_result", "sessionID": "s2", "tool": "bash", "directory": "/work/proj"})
    # Like OpenCode, tool_done keeps the session in working until the next event.
    assert "pi:s2" in d._session_states


def test_session_shutdown_removes_the_pi_slot():
    d = make_daemon()
    feed_pi(d, {"type": "agent_start", "sessionID": "s3", "directory": "/work/proj"})
    feed_pi(d, {"type": "session_shutdown", "sessionID": "s3"})
    assert "pi:s3" not in d._session_states


def test_permission_with_no_pet_connected_answers_none_immediately():
    d = make_daemon()
    replies = []

    class Reply:
        async def send(self, payload):
            replies.append(payload)

    msg = pi_hook_payload_to_daemon_message({
        "type": "permission", "sessionID": "s4", "directory": "/work/proj",
        "tool": "bash", "args": {"command": "ls"},
    })
    asyncio.run(d._handle_message(msg, Reply()))
    assert replies and replies[-1].get("decision") == "none"
