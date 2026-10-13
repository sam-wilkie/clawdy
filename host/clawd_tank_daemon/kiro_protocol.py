"""Translate Kiro IDE hook payloads into the daemon's normalized messages.

Kiro (the AI IDE built on VS Code) exposes lifecycle hooks defined in
``.kiro/hooks/*.json``. A ``command`` hook receives a JSON object on stdin whose
structure mirrors Claude Code's almost one-to-one: ``hook_event_name``,
``session_id``, ``cwd``, ``tool_name``, ``tool_input``, ``tool_response``. This
module reuses the daemon's normalized vocabulary (see the shared contract in
``protocol.hook_payload_to_daemon_message``) so the daemon reacts to a Kiro
session exactly as it does to a Claude Code or Codex one -- no daemon changes
needed.

Payload schema confirmed by capturing live Kiro hook stdin, e.g. PostToolUse::

    {
      "session_id": "sess_c96e417c-0d1e-45ff-8b91-6e558a7c5707",
      "hook_event_name": "PostToolUse",
      "cwd": "o:\\\\Proyectos\\\\Margarita-tank",
      "tool_name": "createHook",
      "tool_input": {...},
      "tool_response": "..."
    }

Kiro trigger names (PascalCase): SessionStart, PreToolUse, PostToolUse, Stop,
UserPromptSubmit, PreTaskExec, PostTaskExec, PostFileCreate, PostFileSave,
PostFileDelete. Kiro has no native PermissionRequest and no
SubagentStart/SubagentStop hooks. Clawdy uses PreToolUse as an explicit desk
approval gate, so every Kiro tool invocation waits for Allow/Deny.

Two Kiro-specific concerns are handled here:
  1. Session IDs are namespaced with a "kiro:" prefix so a Kiro session and a
     Claude/Codex session that share an ID get separate crab slots.
  2. Kiro's tool names (``read_file``, ``fs_write``, ``execute_pwsh``, ...) are
     mapped onto the daemon's existing animation vocabulary. Unmapped tools fall
     through to the daemon's default (typing); any ``mcp__`` prefix is detected
     by the daemon's ``_tool_to_anim`` as the MCP beacon, same as Claude.
"""

from pathlib import Path
from typing import Optional

from .protocol import permission_tool_summary

# Prefix that keeps Kiro session IDs from colliding with Claude Code's or
# Codex's in the daemon's per-session state. The daemon treats session_id as an
# opaque key, so a prefix is enough to give each agent its own crab.
KIRO_SESSION_PREFIX = "kiro:"

# Fixed display name on Kiro notification cards, mirroring protocol.DISPLAY_NAME
# for Claude and CODEX_DISPLAY_NAME for Codex.
KIRO_DISPLAY_NAME = "Kiro"

# Kiro tool name -> the daemon's tool name (which TOOL_ANIMATION_MAP keys on in
# daemon.py). The daemon maps: Edit/Write->typing, Read/Grep/Glob->debugger,
# Bash->building, Agent->conducting, WebSearch/WebFetch->wizard, mcp__*->beacon.
# Anything not listed here and not an mcp__ tool falls through to "typing".
KIRO_TOOL_ALIASES = {
    # File edits / creation -> typing
    "fs_write": "Write",
    "str_replace": "Edit",
    "fs_append": "Edit",
    "create_artifact": "Write",
    "createHook": "Write",
    "semantic_rename": "Edit",
    "smart_relocate": "Edit",
    # Reading / searching the codebase -> debugger
    "read_file": "Read",
    "read_code": "Read",
    "list_directory": "Read",
    "grep_search": "Grep",
    "file_search": "Glob",
    # Shell / process execution -> building
    "execute_pwsh": "Bash",
    "control_pwsh_process": "Bash",
    "get_process_output": "Bash",
    "list_processes": "Bash",
    # Web -> wizard (its failure shows the hat_mishap animation)
    "web_fetch": "WebFetch",
    "remote_web_search": "WebSearch",
    # Sub-agents -> conducting
    "invoke_sub_agent": "Agent",
}


def _kiro_tool_name(raw: str) -> str:
    """Normalize a Kiro tool name to the daemon's vocabulary. An MCP tool keeps
    an ``mcp__`` prefix so the daemon maps it to the beacon animation. Kiro's
    deferred/MCP tools use a ``server::tool`` form, which is normalized to the
    ``mcp__`` prefix the daemon recognizes."""
    if not raw:
        return ""
    if raw.startswith("mcp__"):
        return raw
    # Kiro surfaces MCP/deferred tools as "server::tool"; map to the beacon.
    if "::" in raw:
        return "mcp__" + raw.replace("::", "__")
    return KIRO_TOOL_ALIASES.get(raw, raw)


def _namespaced(session_id: str) -> str:
    """Prefix a Kiro session ID so it never collides with another agent's."""
    sid = session_id or ""
    return f"{KIRO_SESSION_PREFIX}{sid}" if sid else sid


def kiro_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert a Kiro IDE hook stdin payload to a daemon message.

    Mirrors protocol.hook_payload_to_daemon_message but for Kiro's event
    vocabulary. Returns None if the hook event is not relevant (ignored). The
    emitted message uses the SAME schema the daemon already consumes, with a
    namespaced session_id.
    """
    event_name = hook.get("hook_event_name", "")
    session_id = _namespaced(hook.get("session_id", ""))
    cwd = hook.get("cwd", "")
    project = Path(cwd).name if cwd else ""
    # Kiro does not expose a long-lived host PID the way the Claude hook resolver
    # finds claude.exe; omit it. The daemon then evicts the session on the
    # no-PID staleness timeout instead of PID liveness, which is correct here.
    pid = None

    if event_name == "SessionStart":
        msg = {
            "event": "session_start",
            "session_id": session_id,
            "project": project,
            "pid": pid,
        }
        source = hook.get("source")
        if source is not None:
            msg["source"] = source
        return msg

    if event_name == "PreToolUse":
        tool_name = _kiro_tool_name(hook.get("tool_name", ""))
        return {
            "event": "permission",
            "session_id": session_id,
            "tool_name": tool_name,
            "project": project,
            "pid": pid,
            "wait": True,
            "tool_summary": permission_tool_summary(tool_name, hook.get("tool_input")),
        }

    if event_name == "PostToolUse":
        return {
            "event": "tool_done",
            "session_id": session_id,
            "tool_name": _kiro_tool_name(hook.get("tool_name", "")),
            "project": project,
            "pid": pid,
        }

    if event_name == "Stop":
        return {
            "event": "add",
            "hook": "Stop",
            "session_id": session_id,
            "project": KIRO_DISPLAY_NAME,
            "message": "Esperando tu respuesta",
            "pid": pid,
        }

    if event_name == "UserPromptSubmit":
        return {
            "event": "dismiss",
            "hook": "UserPromptSubmit",
            "session_id": session_id,
            "pid": pid,
        }

    if event_name == "SessionEnd":
        msg = {
            "event": "dismiss",
            "hook": "SessionEnd",
            "session_id": session_id,
            "pid": pid,
        }
        reason = hook.get("reason")
        if reason is not None:
            msg["reason"] = reason
        return msg

    return None
