"""Tests for the Kiro IDE hook translator (kiro_protocol)."""

from clawd_tank_daemon.kiro_protocol import (
    kiro_hook_payload_to_daemon_message,
    KIRO_SESSION_PREFIX,
    KIRO_DISPLAY_NAME,
)


def test_session_start_namespaced():
    hook = {
        "hook_event_name": "SessionStart",
        "session_id": "sess_abc",
        "cwd": "o:\\Proyectos\\Margarita-tank",
        "source": "startup",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg is not None
    assert msg["event"] == "session_start"
    # Kiro sessions are namespaced so they never collide with a Claude/Codex id.
    assert msg["session_id"] == KIRO_SESSION_PREFIX + "sess_abc"
    # project is the basename of cwd, even with a Windows-style path.
    assert msg["project"] == "Margarita-tank"
    assert msg["source"] == "startup"


def test_pre_tool_use_execute_pwsh_maps_to_bash():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "execute_pwsh",
        "tool_input": {"command": "Get-ChildItem"},
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    # PreToolUse is a permission request the desktop answers with Allow/Deny.
    assert msg["event"] == "permission"
    assert msg["wait"] is True
    # The summary is built from the already-mapped tool name: Bash -> command.
    assert msg["tool_summary"] == "Get-ChildItem"
    # Kiro "execute_pwsh" -> daemon "Bash" (building animation).
    assert msg["tool_name"] == "Bash"
    assert msg["session_id"] == KIRO_SESSION_PREFIX + "sess_1"


def test_read_file_maps_to_read():
    hook = {
        "hook_event_name": "PostToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "read_file",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "tool_done"
    # read_file -> Read -> debugger animation.
    assert msg["tool_name"] == "Read"


def test_fs_write_maps_to_write():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "fs_write",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "Write"


def test_str_replace_maps_to_edit():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "str_replace",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "Edit"


def test_grep_search_maps_to_grep():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "grep_search",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "Grep"


def test_web_fetch_maps_to_webfetch():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "web_fetch",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "WebFetch"


def test_invoke_sub_agent_maps_to_agent():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "invoke_sub_agent",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "Agent"


def test_mcp_double_colon_tool_becomes_beacon_prefix():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "supabase::query",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    # server::tool -> mcp__server__tool, which _tool_to_anim maps to the beacon.
    assert msg["tool_name"] == "mcp__supabase__query"


def test_mcp_prefix_preserved():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "mcp__server__do_thing",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["tool_name"] == "mcp__server__do_thing"


def test_unknown_tool_passes_through():
    hook = {
        "hook_event_name": "PreToolUse",
        "session_id": "sess_1",
        "cwd": "o:\\tmp",
        "tool_name": "some_future_tool",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    # Unknown tools fall through unchanged; the daemon defaults them to typing.
    assert msg["tool_name"] == "some_future_tool"


def test_stop_is_waiting_card():
    hook = {"hook_event_name": "Stop", "session_id": "sess_1", "cwd": "o:\\tmp"}
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "add"
    assert msg["hook"] == "Stop"
    assert msg["project"] == KIRO_DISPLAY_NAME


def test_prompt_submit_dismiss():
    hook = {"hook_event_name": "UserPromptSubmit", "session_id": "sess_1"}
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "UserPromptSubmit"


def test_session_end_dismiss():
    hook = {
        "hook_event_name": "SessionEnd",
        "session_id": "sess_1",
        "reason": "exit",
    }
    msg = kiro_hook_payload_to_daemon_message(hook)
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "SessionEnd"
    assert msg["reason"] == "exit"


def test_kiro_has_no_permission_or_subagent_events():
    # Kiro exposes neither PermissionRequest nor SubagentStart/Stop hooks, so
    # these must be ignored rather than mistranslated.
    for event in ("PermissionRequest", "SubagentStart", "SubagentStop"):
        assert kiro_hook_payload_to_daemon_message(
            {"hook_event_name": event, "session_id": "sess_1"}
        ) is None


def test_irrelevant_event_ignored():
    assert kiro_hook_payload_to_daemon_message(
        {"hook_event_name": "PostFileSave", "session_id": "sess_1"}
    ) is None


def test_empty_session_id_not_prefixed():
    # Without a session id there is nothing to namespace; stay empty rather than
    # emitting a bare "kiro:" key.
    msg = kiro_hook_payload_to_daemon_message(
        {"hook_event_name": "SessionStart", "session_id": ""}
    )
    assert msg["session_id"] == ""
