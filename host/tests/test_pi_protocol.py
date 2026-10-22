"""Tests for the Pi (gentle-shell) extension event translator (S1, S2, S3)."""

import pytest

from clawd_tank_daemon.pi_protocol import (
    PI_DISPLAY_NAME,
    PI_SESSION_PREFIX,
    pi_hook_payload_to_daemon_message,
)


def _hook(event_type, **extra):
    base = {"type": event_type, "sessionID": "abc", "directory": "/work/proj"}
    base.update(extra)
    return base


def test_session_id_is_namespaced_and_project_is_directory_name():
    msg = pi_hook_payload_to_daemon_message(_hook("session_start"))
    assert msg["session_id"] == PI_SESSION_PREFIX + "abc" == "pi:abc"
    assert msg["project"] == "proj"
    assert msg["pid"] is None


def test_missing_session_id_is_dropped():
    assert pi_hook_payload_to_daemon_message({"type": "session_start"}) is None


def test_session_start_maps_to_session_start():
    assert pi_hook_payload_to_daemon_message(_hook("session_start"))["event"] == "session_start"


def test_agent_start_clears_the_previous_card_like_a_new_prompt():
    msg = pi_hook_payload_to_daemon_message(_hook("agent_start"))
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "UserPromptSubmit"


def test_turn_end_marks_the_session_as_waiting_for_the_user():
    msg = pi_hook_payload_to_daemon_message(_hook("turn_end"))
    assert msg["event"] == "add"
    assert msg["hook"] == "Stop"
    assert msg["message"] == "Esperando tu respuesta"


def test_session_shutdown_removes_the_session():
    msg = pi_hook_payload_to_daemon_message(_hook("session_shutdown"))
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "SessionEnd"


def test_tool_call_and_result_map_to_tool_use_and_tool_done():
    use = pi_hook_payload_to_daemon_message(_hook("tool_call", tool="bash"))
    done = pi_hook_payload_to_daemon_message(_hook("tool_result", tool="bash"))
    assert use["event"] == "tool_use"
    assert done["event"] == "tool_done"
    assert use["tool_name"] == done["tool_name"] == "passthrough"


def test_mcp_tool_keeps_its_prefix_for_the_beacon_animation():
    msg = pi_hook_payload_to_daemon_message(_hook("tool_call", tool="mcp__docs__search"))
    assert msg["tool_name"] == "mcp__docs__search"


def test_permission_request_waits_for_the_pet_decision():
    msg = pi_hook_payload_to_daemon_message(
        _hook("permission", tool="bash", args={"command": "rm -rf build"})
    )
    assert msg["event"] == "permission"
    assert msg["wait"] is True
    assert msg["tool_name"] == "bash"  # shown on the pet's badge, not "passthrough"
    assert "rm -rf build" in msg["tool_summary"]


def test_unknown_event_is_ignored():
    assert pi_hook_payload_to_daemon_message(_hook("message_update")) is None


def test_display_name():
    assert PI_DISPLAY_NAME == "Pi"


def test_daemon_groups_pi_sessions_under_the_pi_product():
    from clawd_tank_daemon.daemon import _session_agent
    assert _session_agent("pi:abc") == "pi"
    assert _session_agent("abc") == "claude"
