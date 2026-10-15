"""Message format conversion between Claude Code hooks, daemon, and BLE."""

import json
from pathlib import Path
from typing import Optional

# Built-in tool whose PreToolUse means "Claude is blocked on a human choice".
# Single source of truth shared by the daemon (state mapping) and the hook
# installer (PostToolUse matcher). Kept here in the shared message module so
# both clawd_tank_daemon and clawd_tank_menubar can import it.
ASK_USER_QUESTION_TOOL = "AskUserQuestion"

# Fixed display name shown on every notification card, regardless of which
# project triggered it. Change this one line to rename the crab in the UI.
DISPLAY_NAME = "Margarita"

# Keep approvals open until a decision or cancellation. None disables the
# bridge/daemon deadline; the host may still enforce its own hook lifetime.
PERMISSION_WAIT_SECONDS = None

# Longest tool summary sent to the desk window (ellipsis included).
PERMISSION_SUMMARY_MAX = 120

# Tools whose summary is the file they act on rather than a command.
_FILE_PATH_TOOLS = frozenset({"Edit", "Write", "Read"})


def permission_tool_summary(tool_name, tool_input) -> str:
    """One short, single-line description of what a tool wants to do, for the
    permission bubble: the command for Bash, the file path for Edit/Write/Read,
    the tool name otherwise. Control characters and newlines become spaces (the
    text is shown on a device and must not carry escape sequences) and the
    result is cut to PERMISSION_SUMMARY_MAX characters with an ellipsis.

    Keep in sync with the copy in hooks.NOTIFY_SCRIPT (it is stdlib-only and
    cannot import this module).
    """
    name = tool_name if isinstance(tool_name, str) else ""
    text = ""
    if isinstance(tool_input, dict):
        if name == "Bash":
            value = tool_input.get("command")
        elif name in _FILE_PATH_TOOLS:
            value = tool_input.get("file_path")
        else:
            value = None
        if isinstance(value, str):
            text = value
    if not text.strip():
        text = name
    text = "".join(c if c.isprintable() else " " for c in text)
    text = " ".join(text.split())
    if len(text) > PERMISSION_SUMMARY_MAX:
        text = text[:PERMISSION_SUMMARY_MAX - 1] + "…"
    return text


def _with_agent_id(msg: dict, hook: dict) -> dict:
    """Tag `msg` with the hook's agent_id when the tool ran inside a subagent.

    Claude Code puts agent_id on every hook fired in a subagent (the main agent's
    own calls have none) but reports it under the PARENT session_id, so without
    this the daemon cannot tell subagent work from the main agent's. The key is
    omitted for the main agent so its messages stay byte-identical."""
    agent_id = hook.get("agent_id")
    if agent_id:
        msg["agent_id"] = agent_id
    return msg


def hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert a Claude Code hook stdin payload to a daemon message.

    Returns None if the hook event is not relevant (should be ignored).
    """
    event_name = hook.get("hook_event_name", "")
    session_id = hook.get("session_id", "")
    cwd = hook.get("cwd", "")
    project = Path(cwd).name if cwd else ""
    pid = hook.get("pid")  # int or None; absent in older notify scripts

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
        return _with_agent_id({
            "event": "tool_use",
            "session_id": session_id,
            "tool_name": hook.get("tool_name", ""),
            "project": project,
            "pid": pid,
        }, hook)

    if event_name == "PostToolUse":
        return _with_agent_id({
            "event": "tool_done",
            "session_id": session_id,
            "tool_name": hook.get("tool_name", ""),
            "project": project,
            "pid": pid,
        }, hook)

    if event_name == "PermissionRequest":
        return _with_agent_id({
            "event": "permission",
            "session_id": session_id,
            "tool_name": hook.get("tool_name", ""),
            "project": project,
            "pid": pid,
            # The hook stays connected and waits for a decision from the desk
            # window; the summary is all of tool_input the daemon ever sees.
            "wait": True,
            "tool_summary": permission_tool_summary(
                hook.get("tool_name", ""), hook.get("tool_input")
            ),
        }, hook)

    if event_name == "PostToolUseFailure":
        return _with_agent_id({
            "event": "tool_failed",
            "session_id": session_id,
            "tool_name": hook.get("tool_name", ""),
            "project": project,
            "pid": pid,
        }, hook)

    if event_name == "PreCompact":
        return {
            "event": "compact",
            "session_id": session_id,
            "pid": pid,
        }

    if event_name == "Stop":
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else "unknown"
        if not project:
            project = "unknown"
        return {
            "event": "add",
            "hook": "Stop",
            "session_id": session_id,
            "project": DISPLAY_NAME,
            "message": "Esperando tu respuesta",
            "pid": pid,
        }

    if event_name == "StopFailure":
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else "unknown"
        if not project:
            project = "unknown"
        message = hook.get("error", "") or hook.get("stop_reason", "") or "Error de API"
        exhausted = classify_exhaustion(hook)
        if exhausted:
            message = exhausted
        out = {
            "event": "add",
            "hook": "StopFailure",
            "session_id": session_id,
            "project": DISPLAY_NAME,
            "message": message,
            "pid": pid,
        }
        if exhausted:
            out["exhausted"] = True
        return out

    if event_name == "Notification":
        if hook.get("notification_type") != "idle_prompt":
            return None
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else "unknown"
        if not project:
            project = "unknown"
        message = hook.get("message", "Esperando tu respuesta")
        return {
            "event": "add",
            "hook": "Notification",
            "session_id": session_id,
            "project": DISPLAY_NAME,
            "message": message,
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

    if event_name == "SubagentStart":
        return {
            "event": "subagent_start",
            "session_id": session_id,
            "agent_id": hook.get("agent_id", ""),
            "pid": pid,
        }

    if event_name == "SubagentStop":
        return {
            "event": "subagent_stop",
            "session_id": session_id,
            "agent_id": hook.get("agent_id", ""),
            "pid": pid,
        }

    return None


# Substrings (matched case-insensitively) of a StopFailure's error fields that
# mean the account ran out of credits / quota. "rate_limit" is Claude Code's
# error-type token for hitting a usage cap; free text like "Rate limit reached"
# is deliberately NOT matched (a transient 429 is not exhaustion).
_EXHAUSTION_FIELDS = ("error", "stop_reason", "error_type", "error_details")
_BILLING_MARKERS = ("credit", "quota", "billing", "insufficient")
_LIMIT_MARKERS = ("usage limit", "usage_limit", "rate_limit")


def classify_exhaustion(hook: dict) -> Optional[str]:
    """Card text if a StopFailure payload reports exhausted credits/quota/usage.

    Returns "Out of credits" for billing-style errors, "Usage limit reached" for
    usage-cap errors, or None when the failure is something else."""
    text = " ".join(str(hook.get(f) or "") for f in _EXHAUSTION_FIELDS).lower()
    if any(m in text for m in _BILLING_MARKERS):
        return "Out of credits"
    if any(m in text for m in _LIMIT_MARKERS):
        return "Usage limit reached"
    return None


def daemon_message_to_ble_payload(msg: dict) -> Optional[str]:
    """Convert a daemon message to a JSON string for BLE GATT write.

    Returns None for session-internal events (session_start, tool_use, tool_done,
    permission, tool_failed, compact, subagent_start, subagent_stop) that have no
    BLE representation. Raises ValueError for unknown events.
    """
    event = msg["event"]

    if event in (
        "session_start", "tool_use", "tool_done", "permission", "tool_failed",
        "compact", "subagent_start", "subagent_stop",
    ):
        return None

    if event == "add":
        payload = {
            "action": "add",
            "id": msg.get("session_id", ""),
            "project": msg.get("project", ""),
            "message": msg.get("message", ""),
        }
        if msg.get("hook") == "StopFailure":
            payload["alert"] = "error"
        return json.dumps(payload)

    if event == "dismiss":
        return json.dumps({
            "action": "dismiss",
            "id": msg.get("session_id", ""),
        })

    # Permission bubble traffic. The daemon queues these for simulator
    # transports only; a BLE device has no bubble and must never get them.
    if event == "permission_request":
        return json.dumps({
            "action": "permission_request",
            "id": msg.get("id", ""),
            "nonce": msg.get("nonce", ""),
            # Which product asked, so the desktop pet shows the bubble over that
            # product's crab window. The SDL2 sim ignores this extra key.
            "agent": msg.get("agent", ""),
            "project": msg.get("project", ""),
            "tool": msg.get("tool", ""),
            "summary": msg.get("summary", ""),
        })

    if event == "permission_clear":
        return json.dumps({"action": "permission_clear", "id": msg.get("id", "")})

    if event == "clear":
        return json.dumps({"action": "clear"})

    raise ValueError(f"Unknown event: {event}")


def usage_to_ble_payload(
    session_pct: Optional[int],
    weekly_pct: Optional[int],
    reset_seconds: Optional[int],
) -> str:
    """Build a set_usage payload. Unknown fields are sent as -1 so the
    firmware/simulator can omit them from the display."""
    return json.dumps({
        "action": "set_usage",
        "session_pct": session_pct if session_pct is not None else -1,
        "weekly_pct": weekly_pct if weekly_pct is not None else -1,
        "reset_s": reset_seconds if reset_seconds is not None else -1,
    })


PROJECT_USAGE_MAX_PROJECTS = 30


def project_usage_to_payload(projects: list) -> str:
    """Build a set_project_usage payload (desktop pet transports only).

    Keeps the 30 projects with the most 30d tokens, dropping those with no
    30d or month usage, so the line stays well under the BLE-sized budget.
    """
    def tokens(w: dict) -> int:
        return w["in"] + w["out"] + w["cw"] + w["cr"]

    live = [p for p in projects if tokens(p["30d"]) or tokens(p["month"])]
    live.sort(key=lambda p: tokens(p["30d"]), reverse=True)
    return json.dumps({
        "action": "set_project_usage",
        "currency": "USD",
        "estimate": True,
        "projects": live[:PROJECT_USAGE_MAX_PROJECTS],
    })


def read_usage_from_cache(cache_path: str) -> Optional[dict]:
    """Read the statusline cache written by the bridge and extract usage.

    Returns a dict {session_pct, weekly_pct, reset_seconds} with None for any
    missing field, or None if the cache is unreadable / has no rate_limits.
    """
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None

    rl = data.get("rate_limits") or {}
    five = rl.get("five_hour") or {}
    seven = rl.get("seven_day") or {}
    if not five and not seven:
        return None

    def as_int(v):
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    session_pct = as_int(five.get("used_percentage"))
    weekly_pct = as_int(seven.get("used_percentage"))

    reset_seconds = None
    resets_at = five.get("resets_at")
    if resets_at is not None:
        import time as _time
        try:
            remaining = int(resets_at) - int(_time.time())
            reset_seconds = max(0, remaining)
        except (TypeError, ValueError):
            reset_seconds = None

    return {
        "session_pct": session_pct,
        "weekly_pct": weekly_pct,
        "reset_seconds": reset_seconds,
    }


def display_state_to_ble_payload(state: dict) -> str:
    """Convert display state dict to v2 JSON payload."""
    if "status" in state:
        return json.dumps({"action": "set_status", "status": state["status"]})
    payload = {"action": "set_sessions", **state}
    return json.dumps(payload)


def display_state_to_v1_payload(state: dict) -> str:
    """Convert display state dict to legacy v1 set_status payload."""
    if "status" in state:
        return json.dumps({"action": "set_status", "status": state["status"]})
    anims = state.get("anims", [])
    # v2-only names fall through to a v1 status: "hat_mishap" counts as
    # confused, "low_battery" and the "happy" oneshot read as idle.
    WORKING_ANIMS = {"typing", "building", "debugger", "wizard", "conducting", "beacon"}
    working = sum(1 for a in anims if a in WORKING_ANIMS)
    if "alert" in anims or "waiting_reply" in anims:
        # "needs your input" is the most actionable signal — outrank busy work.
        # The end-of-turn "waiting_reply" reads the same, as it did before the split.
        status = "confused"
    elif working > 0:
        status = f"working_{min(working, 3)}"
    elif "thinking" in anims:
        status = "thinking"
    elif any(a in ("confused", "dizzy", "hat_mishap") for a in anims):
        status = "confused"
    else:
        status = "idle"
    return json.dumps({"action": "set_status", "status": status})
