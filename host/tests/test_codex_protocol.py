"""Tests for the Codex CLI hook translator (codex_protocol)."""

from clawd_tank_daemon.codex_protocol import (
    codex_hook_payload_to_daemon_message,
    CODEX_SESSION_PREFIX,
    CODEX_DISPLAY_NAME,
)


def test_session_start_namespaced():
    hook = {
        "hook_event_name": "SessionStart",
        "session_id": "cx-1",
        "cwd": "/Users/me/Projects/my-project",
        "matcher": "startup",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg is not None
    assert msg["event"] == "session_start"
    # Codex sessions are namespaced so they never collide with a Claude session id.
    assert msg["session_id"] == CODEX_SESSION_PREFIX + "cx-1"
    assert msg["project"] == "my-project"
    assert msg["source"] == "startup"


def test_pre_tool_use_shell_maps_to_bash():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "cx-1",
        "cwd": "/tmp",
        "tool_name": "shell",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "tool_use"
    # Codex "shell" -> daemon "Bash" (which maps to the building animation).
    assert msg["tool_name"] == "Bash"
    assert msg["session_id"] == CODEX_SESSION_PREFIX + "cx-1"


def test_apply_patch_maps_to_write():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "cx-1",
        "cwd": "/tmp",
        "tool_name": "apply_patch",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "Write"


def test_mcp_tool_prefix_preserved():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "cx-1",
        "cwd": "/tmp",
        "tool_name": "mcp__server__do_thing",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    # The daemon's _tool_to_anim turns any mcp__ prefix into the beacon animation.
    assert msg["tool_name"] == "mcp__server__do_thing"


def test_known_tool_passes_through():
    hook = {
        "hook_event_name": "PostToolUse",
        "session_id": "cx-1",
        "cwd": "/tmp",
        "tool_name": "Edit",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "tool_done"
    assert msg["tool_name"] == "Edit"


def test_permission_request():
    hook = {
        "hook_event_name": "PermissionRequest",
        "session_id": "cx-1",
        "cwd": "/tmp",
        "tool_name": "shell",
    }
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "permission"
    assert msg["tool_name"] == "Bash"


def test_stop_is_waiting_card():
    hook = {"hook_event_name": "Stop", "session_id": "cx-1", "cwd": "/tmp"}
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "add"
    assert msg["hook"] == "Stop"
    assert msg["project"] == CODEX_DISPLAY_NAME


def test_prompt_submit_dismiss():
    hook = {"hook_event_name": "UserPromptSubmit", "session_id": "cx-1"}
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "UserPromptSubmit"


def test_session_end_dismiss():
    hook = {"hook_event_name": "SessionEnd", "session_id": "cx-1", "reason": "exit"}
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "SessionEnd"
    assert msg["reason"] == "exit"


def test_compact_sweeps_but_postcompact_ignored():
    pre = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "PreCompact", "session_id": "cx-1"}
    )
    assert pre["event"] == "compact"
    post = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "PostCompact", "session_id": "cx-1"}
    )
    assert post is None


def test_subagents():
    start = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "SubagentStart", "session_id": "cx-1", "agent_id": "a1"}
    )
    assert start["event"] == "subagent_start"
    assert start["agent_id"] == "a1"
    stop = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "SubagentStop", "session_id": "cx-1", "agent_id": "a1"}
    )
    assert stop["event"] == "subagent_stop"


def test_irrelevant_event_ignored():
    assert codex_hook_payload_to_daemon_message(
        {"hook_event_name": "SomethingElse", "session_id": "cx-1"}
    ) is None


def test_empty_session_id_not_prefixed():
    # Without a session id there is nothing to namespace; stay empty rather than
    # emitting a bare "codex:" key.
    msg = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "SessionStart", "session_id": ""}
    )
    assert msg["session_id"] == ""


# Codex tool name -> daemon vocabulary (TOOL_ANIMATION_MAP keys). Shared with the
# embedded notify script test so the copies cannot drift.
CODEX_ALIAS_CASES = [
    ("shell", "Bash"),
    ("local_shell", "Bash"),
    ("exec_command", "Bash"),
    ("apply_patch", "Write"),
    ("web_search", "WebSearch"),
    ("webrun", "WebSearch"),
    ("view_image", "Read"),
]

# Tools deliberately left as-is (no clear daemon equivalent / must not alert).
CODEX_PASSTHROUGH = ["update_plan", "request_user_input_async", "clocksleep",
                     "Edit", "Bash", "mcp__srv__tool"]


import pytest


@pytest.mark.parametrize("raw,expected", CODEX_ALIAS_CASES)
def test_codex_tool_aliases_map_to_daemon_vocabulary(raw, expected):
    for event_name, event in (("PreToolUse", "tool_use"), ("PermissionRequest", "permission")):
        msg = codex_hook_payload_to_daemon_message(
            {"hook_event_name": event_name, "session_id": "s", "cwd": "/p", "tool_name": raw})
        assert msg["event"] == event and msg["tool_name"] == expected


@pytest.mark.parametrize("raw", CODEX_PASSTHROUGH)
def test_codex_unmapped_tools_pass_through(raw):
    msg = codex_hook_payload_to_daemon_message(
        {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/p", "tool_name": raw})
    assert msg["tool_name"] == raw


def test_every_alias_target_has_a_daemon_animation():
    from clawd_tank_daemon.daemon import TOOL_ANIMATION_MAP
    from clawd_tank_daemon.codex_protocol import CODEX_TOOL_ALIASES
    for target in CODEX_TOOL_ALIASES.values():
        assert target in TOOL_ANIMATION_MAP
