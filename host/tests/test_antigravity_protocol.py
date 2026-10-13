"""Tests for the Antigravity (agy CLI + Antigravity IDE) hook payload translator.

Payload shapes were captured live from agy 1.1.7 and the Antigravity IDE. The
hook stdin is camelCase JSON; the event name is not part of it, so the notify
script injects it as ``hookEventName`` from the installed hook command.
"""

import pytest

from clawd_tank_daemon.antigravity_protocol import (
    ANTIGRAVITY_SESSION_PREFIX,
    antigravity_hook_payload_to_daemon_message,
)

CLI_TRANSCRIPT = (
    "C:/Users/Matt/.gemini/antigravity-cli/brain/abc/.system_generated/logs/"
    "transcript_full.jsonl"
)
IDE_TRANSCRIPT = (
    "C:/Users/Matt/.gemini/antigravity-ide/brain/abc/.system_generated/logs/"
    "transcript_full.jsonl"
)


def hook(event, **fields):
    base = {
        "hookEventName": event,
        "conversationId": "abc",
        "workspacePaths": ["C:/work/proj"],
        "transcriptPath": CLI_TRANSCRIPT,
        "artifactDirectoryPath": "C:/Users/Matt/.gemini/antigravity-cli/brain/abc",
        "modelName": "gemini-3",
    }
    base.update(fields)
    return base


def test_pre_tool_use_becomes_namespaced_tool_use():
    msg = antigravity_hook_payload_to_daemon_message(
        hook("PreToolUse", toolCall={"name": "run_command", "args": {}}, stepIdx=3)
    )
    assert msg == {
        "event": "tool_use",
        "session_id": ANTIGRAVITY_SESSION_PREFIX + "abc",
        "tool_name": "Bash",
        "project": "proj",
        "pid": None,
    }
    assert ANTIGRAVITY_SESSION_PREFIX == "antigravity:"


@pytest.mark.parametrize("raw,expected", [
    ("view_file", "Read"),
    ("list_dir", "Read"),
    ("find_by_name", "Glob"),
    ("grep_search", "Grep"),
    ("write_to_file", "Write"),
    ("replace_file_content", "Edit"),
    ("multi_replace_file_content", "Edit"),
    ("run_command", "Bash"),
    ("search_web", "WebSearch"),
    ("read_url_content", "WebFetch"),
    ("invoke_subagent", "Agent"),
    ("manage_subagents", "Agent"),
    ("ask_question", "AskUserQuestion"),
    ("ask_permission", "AskUserQuestion"),
    ("manage_task", "passthrough"),
    ("schedule", "passthrough"),
    ("generate_image", "passthrough"),
    ("brand_new_tool", "passthrough"),
    ("mcp__server__tool", "mcp__server__tool"),
])
def test_tool_names_map_to_the_daemon_vocabulary(raw, expected):
    msg = antigravity_hook_payload_to_daemon_message(
        hook("PreToolUse", toolCall={"name": raw, "args": {}})
    )
    assert msg["tool_name"] == expected


def test_pre_invocation_means_thinking():
    msg = antigravity_hook_payload_to_daemon_message(
        hook("PreInvocation", invocationNum=1, initialNumSteps=0)
    )
    assert msg == {
        "event": "dismiss",
        "hook": "UserPromptSubmit",
        "session_id": "antigravity:abc",
        "project": "proj",
        "pid": None,
    }


def test_post_tool_use_becomes_tool_done():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "PostToolUse", stepIdx=3,
        toolCall={"name": "view_file",
                  "args": {"toolAction": "Viewing", "toolSummary": "a.py"}},
    ))
    assert msg == {
        "event": "tool_done",
        "session_id": "antigravity:abc",
        "tool_name": "Read",
        "project": "proj",
        "pid": None,
    }


def test_post_tool_use_with_error_becomes_tool_failed():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "PostToolUse", error="boom",
        toolCall={"name": "search_web", "args": {}},
    ))
    assert msg["event"] == "tool_failed"
    assert msg["tool_name"] == "WebSearch"


def test_post_tool_use_with_empty_error_is_still_tool_done():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "PostToolUse", error="", toolCall={"name": "run_command", "args": {}},
    ))
    assert msg["event"] == "tool_done"


def test_stop_fully_idle_is_end_of_turn():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", executionNum=1, terminationReason="NO_TOOL_CALL",
        error="", fullyIdle=True,
    ))
    assert msg["event"] == "add"
    assert msg["hook"] == "Stop"
    assert msg["session_id"] == "antigravity:abc"
    assert msg["pid"] is None
    assert msg["project"] == "proj"


def test_stop_with_background_work_does_not_end_the_turn():
    assert antigravity_hook_payload_to_daemon_message(hook(
        "Stop", terminationReason="NO_TOOL_CALL", error="", fullyIdle=False,
    )) is None


def test_stop_without_fully_idle_field_ends_the_turn():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", terminationReason="model_stop", error="",
    ))
    assert msg["hook"] == "Stop"


@pytest.mark.parametrize("transcript,card", [
    (CLI_TRANSCRIPT, "Antigravity CLI"),
    (IDE_TRANSCRIPT, "Antigravity IDE"),
    ("", "Antigravity"),
    ("D:/somewhere/else.jsonl", "Antigravity"),
])
def test_card_name_tells_cli_from_ide_by_transcript_path(transcript, card):
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", fullyIdle=True, transcriptPath=transcript, workspacePaths=[],
    ))
    assert msg["project"] == card
    assert msg["project_fallback"] is True


def test_stop_with_error_is_an_error_state_card():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", terminationReason="error", error="upstream exploded",
        fullyIdle=True,
    ))
    assert msg["event"] == "add"
    assert msg["hook"] == "StopFailure"
    assert msg["message"] == "upstream exploded"
    assert msg["project"] == "proj"
    assert "exhausted" not in msg


def test_stop_error_wins_even_when_background_work_is_running():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", error="bad", fullyIdle=False,
    ))
    assert msg["hook"] == "StopFailure"


def test_stop_with_termination_reason_error_but_no_text_still_errors():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", terminationReason="error", error="", fullyIdle=True,
    ))
    assert msg["hook"] == "StopFailure"
    assert msg["message"]  # never an empty card


def test_stop_error_about_credits_is_flagged_exhausted():
    msg = antigravity_hook_payload_to_daemon_message(hook(
        "Stop", terminationReason="error",
        error="You have run out of credits", fullyIdle=True,
    ))
    assert msg["message"] == "Out of credits"
    assert msg["exhausted"] is True


@pytest.mark.parametrize("event", ["PostInvocation", "SessionStart", "Nope", ""])
def test_irrelevant_events_are_ignored(event):
    assert antigravity_hook_payload_to_daemon_message(hook(event)) is None


def test_payload_without_conversation_id_is_dropped():
    assert antigravity_hook_payload_to_daemon_message(
        hook("PreInvocation", conversationId="")
    ) is None


def test_project_is_empty_when_the_ide_has_no_folder_open():
    msg = antigravity_hook_payload_to_daemon_message(
        hook("PreInvocation", workspacePaths=[])
    )
    assert msg["project"] == ""


def test_project_is_empty_when_workspace_paths_is_missing_or_null():
    for value in (None, "missing"):
        payload = hook("PreInvocation", workspacePaths=value)
        if value == "missing":
            del payload["workspacePaths"]
        assert antigravity_hook_payload_to_daemon_message(payload)["project"] == ""


def test_tool_call_missing_yields_empty_tool_name():
    msg = antigravity_hook_payload_to_daemon_message(hook("PreToolUse"))
    assert msg["tool_name"] == ""


def test_stop_with_a_workspace_is_titled_by_the_folder_not_the_product():
    msg = antigravity_hook_payload_to_daemon_message(hook("Stop", fullyIdle=True))
    assert msg["project"] == "proj"
    assert "project_fallback" not in msg


def test_stop_without_a_workspace_falls_back_to_the_display_name():
    msg = antigravity_hook_payload_to_daemon_message(
        hook("Stop", fullyIdle=True, workspacePaths=[]))
    assert msg["project"] == "Antigravity CLI"
    assert msg["project_fallback"] is True


def test_stop_failure_follows_the_same_project_rules():
    with_ws = antigravity_hook_payload_to_daemon_message(
        hook("Stop", error="boom", fullyIdle=True))
    assert (with_ws["hook"], with_ws["project"]) == ("StopFailure", "proj")
    without = antigravity_hook_payload_to_daemon_message(
        hook("Stop", error="boom", fullyIdle=True, workspacePaths=[],
             transcriptPath=IDE_TRANSCRIPT))
    assert without["project"] == "Antigravity IDE"
    assert without["project_fallback"] is True
