"""Translate Pi (gentle-shell) extension event payloads into daemon messages.

Pi's extension API emits lifecycle events (``session_start``, ``agent_start``,
``turn_end``, ``agent_end``, ``session_shutdown``) and tool events
(``tool_call``, ``tool_result``). Permission prompts come from the extension
itself, which asks the pet before a tool runs and blocks the call on deny.

This module reuses the daemon's normalized vocabulary (see
``protocol.hook_payload_to_daemon_message``) so a Pi session reacts exactly
like the other products. Session IDs carry a ``pi:`` prefix so a Pi session
never shares a slot with another agent.

The extension ships a stdlib-only copy of this logic inside the notify script
(``hooks.NOTIFY_SCRIPT``). Keep both copies in sync.
"""

from pathlib import Path
from typing import Optional

from .protocol import permission_tool_summary

# Matches the ("pi:", "pi") tuple in daemon.SESSION_AGENT_PREFIXES.
PI_SESSION_PREFIX = "pi:"

# Display name used on notification cards.
PI_DISPLAY_NAME = "Pi"


def _namespaced(session_id: str) -> str:
    sid = session_id or ""
    return f"{PI_SESSION_PREFIX}{sid}" if sid else ""


def _tool_name(raw: str) -> str:
    """Keep MCP names so the daemon maps them to the beacon; everything else is
    'passthrough', which the daemon animates as typing."""
    if not raw:
        return ""
    if raw.startswith("mcp__"):
        return raw
    return "passthrough"


def pi_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert one Pi extension payload to a daemon message, or None if the
    daemon does not act on it or the payload has no session id."""
    event_type = hook.get("type", "")
    session_id = _namespaced(hook.get("sessionID", "") or hook.get("session_id", ""))
    # Without a session id the daemon would create a ghost slot keyed by "".
    if not session_id:
        return None

    directory = hook.get("directory", "") or hook.get("cwd", "")
    project = Path(directory).name if directory else ""
    # Pi has no long-lived PID the daemon can watch; it evicts on the no-PID timeout.
    pid = None

    if event_type == "session_start":
        return {"event": "session_start", "session_id": session_id,
                "project": project, "pid": pid}

    if event_type == "agent_start":
        return {"event": "dismiss", "hook": "UserPromptSubmit",
                "session_id": session_id, "project": project, "pid": pid}

    if event_type == "turn_end":
        return {"event": "add", "hook": "Stop", "session_id": session_id,
                "project": project, "pid": pid, "message": "Esperando tu respuesta"}

    if event_type == "session_shutdown":
        return {"event": "dismiss", "hook": "SessionEnd",
                "session_id": session_id, "pid": pid}

    if event_type == "tool_call":
        return {"event": "tool_use", "session_id": session_id,
                "tool_name": _tool_name(hook.get("tool", "")),
                "project": project, "pid": pid}

    if event_type == "tool_result":
        return {"event": "tool_done", "session_id": session_id,
                "tool_name": _tool_name(hook.get("tool", "")),
                "project": project, "pid": pid}

    if event_type == "permission":
        raw_tool = hook.get("tool", "")
        # permission_tool_summary matches Claude's capitalized names ("Bash"), so map Pi's bash to it.
        summary_name = "Bash" if raw_tool == "bash" else raw_tool
        return {"event": "permission", "session_id": session_id,
                "tool_name": _tool_name(raw_tool), "project": project, "pid": pid,
                "wait": True,
                "tool_summary": permission_tool_summary(summary_name, hook.get("args"))}

    return None
