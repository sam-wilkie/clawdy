"""Tests for the OpenCode plugin event translator.

Mirrors the structure of `tests/test_codex_protocol.py` / `test_kiro_protocol.py`
and exercises the OpenCode event vocabulary defined in the opencode-product
change. Every translated message uses the "opencode:" session-id namespace so
the daemon can distinguish OpenCode sessions from Claude/Codex/Kiro ones.
"""

import pytest

from clawd_tank_daemon.opencode_protocol import (
    OPENCODE_DISPLAY_NAME,
    OPENCODE_SESSION_PREFIX,
    opencode_hook_payload_to_daemon_message,
)


# --- session.created → session_start -----------------------------------------

@pytest.mark.parametrize("event_type,event,hook", [
    ("chat.message", "dismiss", "UserPromptSubmit"),
    ("session.idle", "add", "Stop"),
    ("session.heartbeat", "session_heartbeat", None),
])
def test_v2_prompt_and_idle_keep_opencode_identity(event_type, event, hook):
    msg = opencode_hook_payload_to_daemon_message({
        "type": event_type, "sessionID": "restored", "directory": "/work/project",
    })
    assert msg["event"] == event
    assert msg.get("hook") == hook
    assert msg["session_id"] == "opencode:restored"
    assert msg["project"] == "project"
    # The installed standalone bridge must recognize the same v2 events.
    from clawd_tank_menubar.hooks import NOTIFY_SCRIPT
    namespace = {"__name__": "bridge_test"}
    exec(NOTIFY_SCRIPT, namespace)
    assert namespace["opencode_hook_to_message"]({
        "type": event_type, "sessionID": "restored", "directory": "/work/project",
    }) == msg
    from tests.test_notify_standalone import _load_notify_script
    standalone = _load_notify_script()
    assert standalone._parse_source(["opencode"]) == "opencode"
    assert standalone._translate_payload({
        "type": event_type, "sessionID": "restored", "directory": "/work/project",
    }, "opencode") == msg

def test_session_created_translates_to_session_start_with_prefix():
    """session.created maps to session_start, session_id is namespaced with the
    OpenCode prefix, and pid is None (OpenCode has no hostable PID)."""
    payload = {"type": "session.created", "sessionID": "abc123",
               "directory": "/home/u/project"}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "session_start"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc123"
    # project comes from the directory basename (mirrors codex_protocol)
    assert msg["project"] == "project"
    assert msg["pid"] is None


def test_session_created_passthrough_of_source_field():
    """A `source` metadata field on session.created carries over, mirroring
    Codex's source/matcher passthrough behaviour."""
    payload = {"type": "session.created", "sessionID": "abc", "source": "tui"}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg["event"] == "session_start"
    assert msg.get("source") == "tui"


# --- session.deleted → dismiss ----------------------------------------------

def test_session_deleted_translates_to_dismiss():
    """session.deleted maps to dismiss with hook=SessionEnd (so the daemon
    removes the session, not just the notification card)."""
    payload = {"type": "session.deleted", "sessionID": "abc123"}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "dismiss"
    assert msg["hook"] == "SessionEnd"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc123"
    assert msg["pid"] is None


# --- tool.execute.before → tool_use -----------------------------------------

def test_tool_execute_before_translates_to_tool_use_with_passthrough_tool():
    """tool.execute.before maps to tool_use. The stubbed OPENCODE_TOOL_ALIASES
    dict is empty, so an unknown tool name falls through to "passthrough" (which
    the daemon's _tool_to_anim resolves to "typing")."""
    payload = {"type": "tool.execute.before", "sessionID": "abc",
               "tool": "some_opencode_tool", "callID": "call-1"}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "tool_use"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc"
    assert msg["tool_name"] == "passthrough"
    assert msg["pid"] is None


# --- tool.execute.after → tool_done -----------------------------------------

def test_tool_execute_after_translates_to_tool_done_with_passthrough_tool():
    payload = {"type": "tool.execute.after", "sessionID": "abc",
               "tool": "another_tool", "callID": "call-1", "args": {}}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "tool_done"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc"
    assert msg["tool_name"] == "passthrough"
    assert msg["pid"] is None


# --- permission.ask → permission ---------------------------------------------

def test_permission_ask_translates_to_permission_with_wait_true_and_summary():
    """permission.ask maps to a permission message that blocks on the desk
    window's decision (wait=True), with a tool_summary for the bubble.

    With OPENCODE_TOOL_ALIASES stubbed to {}, the unknown tool name falls
    through to "passthrough"; permission_tool_summary sees the tool name does
    not match Bash/Edit/Write/Read, so the summary is the tool name itself.
    """
    payload = {"type": "permission.ask", "sessionID": "abc",
               "tool": "some_opencode_tool",
               "args": {"command": "rm -rf /"}}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "permission"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc"
    assert msg["tool_name"] == "passthrough"
    assert msg["wait"] is True
    # summary present; with the empty alias stub the summary IS the tool name
    assert "tool_summary" in msg
    assert msg["tool_summary"] == "passthrough"
    assert msg["pid"] is None


# --- experimental.session.compacting → compact ------------------------------

def test_session_compacting_translates_to_compact():
    payload = {"type": "experimental.session.compacting", "sessionID": "abc"}
    msg = opencode_hook_payload_to_daemon_message(payload)
    assert msg is not None
    assert msg["event"] == "compact"
    assert msg["session_id"] == f"{OPENCODE_SESSION_PREFIX}abc"
    assert msg["pid"] is None


# --- Unknown / irrelevant events return None --------------------------------

def test_unknown_event_type_returns_none():
    """A hook whose `type` is not one of the six mapped events is dropped (the
    OpenCode runtime may emit others we do not act on)."""
    payload = {"type": "file.watcher.changed", "sessionID": "abc", "path": "/x"}
    assert opencode_hook_payload_to_daemon_message(payload) is None


# --- Empty / missing session_id returns None ---------------------------------

def test_missing_session_id_returns_none():
    """An event without a sessionID is dropped, not sent to the daemon with an
    empty key (the daemon keys its state by session_id)."""
    payload = {"type": "session.created"}  # no sessionID
    assert opencode_hook_payload_to_daemon_message(payload) is None


# --- Display name constant is set (used by future card rendering) ----------

def test_opencode_display_name_constant():
    assert OPENCODE_DISPLAY_NAME == "OpenCode"


# --- Module-level constants -------------------------------------------------

def test_session_prefix_constant():
    assert OPENCODE_SESSION_PREFIX == "opencode:"
