"""Translate OpenCode plugin hook payloads into the daemon's normalized messages.

OpenCode's plugin API (`@opencode-ai/plugin` v1.17.15) exposes lifecycle hooks
whose event names and JSON shapes do NOT overlap with Claude Code's hook
vocabulary: OpenCode ships its own router (`event` with `type` /
`sessionID` / `directory`) and per-tool hooks (`tool.execute.before` /
`tool.execute.after`, `permission.ask`, `experimental.session.compacting`).
This module reuses the daemon's normalized vocabulary (see the shared contract
in ``protocol.hook_payload_to_daemon_message``) so the daemon reacts to an
OpenCode session exactly as it does to a Claude/Codex/Kiro one -- no daemon
state-machine changes needed.

Three OpenCode-specific concerns are handled here:

  1. Session IDs are namespaced with an ``opencode:`` prefix so an OpenCode
     session and a Claude/Codex/Kiro session that happen to share an ID get
     separate crab slots. ``SESSION_AGENT_PREFIXES`` in ``daemon.py`` carries
     ``("opencode:", "opencode")`` as the matching tuple.
  2. ``pid`` is always ``None``: OpenCode has no hostable long-lived PID the
     way the Claude hook resolver finds ``claude.exe``; the daemon evicts
     OpenCode sessions on the shorter no-PID staleness timeout
     (``NO_PID_STALENESS_TIMEOUT``), same as those products.
  3. OpenCode tool names are mapped to the daemon's vocabulary through
     ``OPENCODE_TOOL_ALIASES``. The map is **declared but empty** -- a TODO
     marker notes the values will be populated empirically in the spec phase --
     so unknown tools fall through to ``"passthrough"``, which the daemon's
     ``_tool_to_anim`` resolves to ``"typing"``. ``mcp__``-prefixed names keep
     their prefix so the daemon maps them to the beacon animation.

This module is the daemon-side translator. The Python bridge
(``~/.clawd-tank/opencode-bridge.py``) carries an inlined copy of this logic
because the bridge is stdlib-only and cannot import the daemon package.
Keep both copies in sync.
"""

from pathlib import Path
from typing import Optional

from .protocol import permission_tool_summary

# Prefix that keeps OpenCode session IDs from colliding with Claude/Codex/Kiro's
# in the daemon's per-session state. The daemon treats ``session_id`` as an
# opaque key, so a prefix is enough to give each agent its own crab. The
# matching tuple ``("opencode:", "opencode")`` lives in
# ``daemon.SESSION_AGENT_PREFIXES`` and is the single source of truth for the
# desktop pet's product slot.
OPENCODE_SESSION_PREFIX = "opencode:"

# Fixed display name on OpenCode notification cards, mirroring
# ``protocol.DISPLAY_NAME`` (Claude), ``CODEX_DISPLAY_NAME`` (Codex) and
# ``KIRO_DISPLAY_NAME`` (Kiro). Kept here so the OpenCode card can read
# differently if desired later.
OPENCODE_DISPLAY_NAME = "OpenCode"

# OpenCode tool name -> the daemon's tool name (which ``TOOL_ANIMATION_MAP``
# keys on in ``daemon.py``). Unknown tools fall through to ``"passthrough"``,
# which the daemon's ``_tool_to_anim`` maps to ``"typing"``; ``mcp__``-prefixed
# names are detected by the daemon as the MCP beacon, same as Claude/Codex/Kiro.
#
# TODO [spec-phase]: Populate from OpenCode docs + live session capture. The
# values land here as soon as the first OpenCode session emits a real tool
# name; tests may mutate this dict to cover specific mappings.
OPENCODE_TOOL_ALIASES: dict = {}


def _opencode_tool_name(raw: str) -> str:
    """Normalize an OpenCode tool name to the daemon's vocabulary. An MCP tool
    keeps its ``mcp__`` prefix so the daemon maps it to the beacon animation;
    anything else falls through to ``OPENCODE_TOOL_ALIASES.get(raw, "passthrough")``
    -- so when the alias map is empty (MVP stub), every non-mcp tool becomes
    ``"passthrough"`` and animates as ``"typing"`` until live data lands.
    """
    if not raw:
        return ""
    if raw.startswith("mcp__"):
        return raw
    return OPENCODE_TOOL_ALIASES.get(raw, "passthrough")


def _namespaced(session_id: str) -> str:
    """Prefix an OpenCode session ID so it never collides with another agent's."""
    sid = session_id or ""
    return f"{OPENCODE_SESSION_PREFIX}{sid}" if sid else ""


def opencode_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert an OpenCode plugin hook payload to a daemon message.

    Mirrors ``codex_hook_payload_to_daemon_message`` / ``kiro_hook_payload_to_daemon_message``
    but for OpenCode's event vocabulary (``session.created`` /
    ``session.deleted`` / ``tool.execute.before`` / ``tool.execute.after`` /
    ``permission.ask`` / ``experimental.session.compacting``). Returns ``None``
    for events that are not relevant (the OpenCode runtime fires many other
    hooks the daemon does not act on) and for payloads without a session id.
    The emitted message uses the SAME schema the daemon already consumes, with
    a namespaced session_id and ``pid=None``.
    """
    event_type = hook.get("type", "")
    raw_session_id = hook.get("sessionID", "") or hook.get("session_id", "")
    session_id = _namespaced(raw_session_id)
    # An event without a session id is dropped: the daemon keys its state by
    # ``session_id``, so sending an empty key would create a ghost slot.
    if not session_id:
        return None

    directory = hook.get("directory", "") or hook.get("cwd", "")
    project = Path(directory).name if directory else ""
    # OpenCode has no hostable long-lived PID the way the Claude hook resolver
    # finds ``claude.exe``; the daemon evicts OpenCode sessions on the shorter
    # no-PID staleness timeout (``NO_PID_STALENESS_TIMEOUT``) instead.
    pid = None

    if event_type == "session.created":
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

    if event_type == "session.deleted":
        # Mirror Codex/Kiro's SessionEnd: include `hook: "SessionEnd"` so the
        # daemon's _handle_message removes the session entirely (a plain
        # `event: "dismiss"` only clears the active notification card).
        return {
            "event": "dismiss",
            "hook": "SessionEnd",
            "session_id": session_id,
            "pid": pid,
        }

    if event_type == "tool.execute.before":
        return {
            "event": "tool_use",
            "session_id": session_id,
            "tool_name": _opencode_tool_name(hook.get("tool", "")),
            "project": project,
            "pid": pid,
        }

    if event_type == "tool.execute.after":
        return {
            "event": "tool_done",
            "session_id": session_id,
            "tool_name": _opencode_tool_name(hook.get("tool", "")),
            "project": project,
            "pid": pid,
        }

    if event_type == "permission.ask":
        tool_name = _opencode_tool_name(hook.get("tool", ""))
        return {
            "event": "permission",
            "session_id": session_id,
            "tool_name": tool_name,
            "project": project,
            "pid": pid,
            "wait": True,
            "tool_summary": permission_tool_summary(tool_name, hook.get("args")),
        }

    if event_type == "experimental.session.compacting":
        return {
            "event": "compact",
            "session_id": session_id,
            "pid": pid,
        }

    return None