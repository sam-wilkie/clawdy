"""Translate Antigravity (agy CLI + Antigravity IDE) hook payloads into the
daemon's normalized messages.

Antigravity hooks pipe a camelCase JSON document on stdin (``conversationId``,
``workspacePaths``, ``transcriptPath``, ``modelName`` ... on every event). The
event name is NOT part of that document, so the installed hook command passes
it as an argument and the notify script injects it as ``hookEventName``.

Antigravity-specific concerns handled here:

  1. Session IDs are namespaced ``antigravity:`` + conversationId, so a
     conversation never collides with a Claude/Codex/Kiro/OpenCode session.
     ``SESSION_AGENT_PREFIXES`` in ``daemon.py`` carries the matching tuple.
  2. There is no SessionStart/SessionEnd and no PID. The daemon creates the
     session on the first ``tool_use`` / thinking event (it is tolerant of an
     implicit start) and evicts it on the no-PID staleness timeout.
  3. Tool names are mapped onto the daemon's vocabulary (``TOOL_ANIMATION_MAP``);
     unknown tools become ``"passthrough"`` (typing), ``mcp__`` names keep their
     prefix (beacon).

The notify script carries an inlined copy of this logic (it is stdlib-only and
cannot import the daemon package). Keep both copies in sync.
"""

from pathlib import Path
from typing import Optional

from .protocol import ASK_USER_QUESTION_TOOL, classify_exhaustion

ANTIGRAVITY_SESSION_PREFIX = "antigravity:"

# Card names. The transcript path tells the two products apart
# (``.../.gemini/antigravity-cli/...`` vs ``.../.gemini/antigravity-ide/...``);
# both share one session prefix and one crab, only the card text differs.
ANTIGRAVITY_DISPLAY_NAME = "Antigravity"
ANTIGRAVITY_CLI_DISPLAY_NAME = "Antigravity CLI"
ANTIGRAVITY_IDE_DISPLAY_NAME = "Antigravity IDE"

# Antigravity tool name -> the daemon's tool name. ask_question and
# ask_permission block on the human, so they reuse the AskUserQuestion name the
# daemon already surfaces as the "waiting" (alert) state. Anything unlisted
# falls through to "passthrough" (typing).
ANTIGRAVITY_TOOL_ALIASES = {
    "view_file": "Read",
    "list_dir": "Read",
    "find_by_name": "Glob",
    "grep_search": "Grep",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "Edit",
    "run_command": "Bash",
    "search_web": "WebSearch",
    "read_url_content": "WebFetch",
    "invoke_subagent": "Agent",
    "manage_subagents": "Agent",
    "ask_question": ASK_USER_QUESTION_TOOL,
    "ask_permission": ASK_USER_QUESTION_TOOL,
}


def _antigravity_tool_name(raw: str) -> str:
    if not raw:
        return ""
    if raw.startswith("mcp__"):
        return raw
    return ANTIGRAVITY_TOOL_ALIASES.get(raw, "passthrough")


def _display_name(hook: dict) -> str:
    transcript = str(hook.get("transcriptPath") or "").replace("\\", "/")
    if "antigravity-cli" in transcript:
        return ANTIGRAVITY_CLI_DISPLAY_NAME
    if "antigravity-ide" in transcript:
        return ANTIGRAVITY_IDE_DISPLAY_NAME
    return ANTIGRAVITY_DISPLAY_NAME


def _stop_project_fields(hook: dict, project: str) -> dict:
    """Project fields for an end-of-turn card: the workspace folder when known,
    else the product name, flagged so the daemon never lets it replace a real
    project already stored on the session."""
    if project:
        return {"project": project}
    return {"project": _display_name(hook), "project_fallback": True}


def antigravity_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert an Antigravity hook stdin payload to a daemon message, or None
    for events/payloads the daemon does not act on."""
    event_name = hook.get("hookEventName", "")
    conversation_id = hook.get("conversationId", "")
    if not conversation_id:
        return None
    session_id = ANTIGRAVITY_SESSION_PREFIX + conversation_id
    workspaces = hook.get("workspacePaths") or []
    project = Path(workspaces[0]).name if workspaces else ""

    if event_name == "PreInvocation":
        # The model is about to be called. The daemon's "UserPromptSubmit"
        # dismiss is what puts a session (creating it if need be) in "thinking".
        return {
            "event": "dismiss",
            "hook": "UserPromptSubmit",
            "session_id": session_id,
            "project": project,
            "pid": None,
        }

    if event_name == "PreToolUse":
        tool_call = hook.get("toolCall") or {}
        return {
            "event": "tool_use",
            "session_id": session_id,
            "tool_name": _antigravity_tool_name(tool_call.get("name", "")),
            "project": project,
            "pid": None,
        }

    if event_name == "PostToolUse":
        tool_call = hook.get("toolCall") or {}
        return {
            # A non-empty error is a genuine tool failure (the daemon shows a
            # transient "confused"); otherwise the tool simply finished.
            "event": "tool_failed" if hook.get("error") else "tool_done",
            "session_id": session_id,
            "tool_name": _antigravity_tool_name(tool_call.get("name", "")),
            "project": project,
            "pid": None,
        }

    if event_name == "Stop":
        error = hook.get("error") or ""
        if error or hook.get("terminationReason") == "error":
            # The turn died on an error: same card as Claude's StopFailure.
            exhausted = classify_exhaustion(hook)
            msg = {
                "event": "add",
                "hook": "StopFailure",
                "session_id": session_id,
                **_stop_project_fields(hook, project),
                "message": exhausted or error or "Agent error",
                "pid": None,
            }
            if exhausted:
                msg["exhausted"] = True
            return msg
        if hook.get("fullyIdle") is False:
            # Background tasks are still running: the turn is not over.
            return None
        return {
            "event": "add",
            "hook": "Stop",
            "session_id": session_id,
            **_stop_project_fields(hook, project),
            "message": "Waiting for your reply",
            "pid": None,
        }

    return None
