# host/clawd_tank_menubar/hooks.py
"""Install the Claude Code hook script and configure hooks in settings."""

import copy
import json
import logging
import ntpath
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from clawd_tank_daemon.protocol import (
    ASK_USER_QUESTION_TOOL,
    DISPLAY_NAME,
    PERMISSION_WAIT_SECONDS,
)

from .version import get_version

logger = logging.getLogger("clawd-tank.hooks")

CLAWD_DIR = Path.home() / ".clawd-tank"
# Windows cannot execute an extensionless file with a shebang, and the command
# below names the interpreter explicitly, so the script needs the .py suffix
# for that interpreter to accept it.
NOTIFY_SCRIPT_PATH = CLAWD_DIR / (
    "clawd-tank-notify.py" if sys.platform == "win32" else "clawd-tank-notify"
)
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# Hosts require a finite hook timeout. Allow a day to answer at the pet instead
# of withdrawing its buttons after a few seconds; cancellation still ends early.
PERMISSION_HOOK_TIMEOUT_SECONDS = 86400

# Windows runs the Python bridge through an explicit interpreter, so it needs the
# .py suffix; macOS and Linux run a plain sh script and need no Python at all.
LEGACY_STATUSLINE_SCRIPT_NAME = "statusline_bridge.py"  # what POSIX ran before the sh bridge
STATUSLINE_SCRIPT_PATH = CLAWD_DIR / (
    LEGACY_STATUSLINE_SCRIPT_NAME if sys.platform == "win32" else "statusline_bridge.sh"
)
# The user's pre-existing statusLine, saved so the bridge can chain it and
# uninstall can restore it exactly.
STATUSLINE_STATE_NAME = "statusline-original.json"
# The same saved command as plain text, written verbatim. The POSIX sh bridge
# reads this instead of picking the string out of the JSON: it has no JSON parser.
STATUSLINE_COMMAND_NAME = "statusline-original.txt"
STATUSLINE_EXE_NAME = "margarita-statusline.exe"

# Standalone hook script — uses only Python stdlib, no external imports.
NOTIFY_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """clawd-tank-notify - Claude Code hook handler for Clawd Tank.

    Reads hook payload from stdin, converts it to a daemon message, and forwards
    it to the daemon: a Unix socket on POSIX, an authenticated loopback TCP
    connection on Windows. No external dependencies.
    """
    # NOTIFY_SCRIPT_VERSION: 2026-10-11-subagent-agent-id

    import json
    import os
    import re
    import socket
    import subprocess
    import sys
    import time
    from pathlib import Path

    # Fixed name on every notification card (protocol.DISPLAY_NAME).
    DISPLAY_NAME = __DISPLAY_NAME__

    # No bridge deadline: keep the pet's decision channel open until answered.
    PERMISSION_WAIT_SECONDS = None
    # CLAWD_PERMISSION_WAIT supplies a finite wait for tests/debugging.
    PERMISSION_WAIT_ENV = "CLAWD_PERMISSION_WAIT"
    PERMISSION_DENY_MESSAGE = "Denied from Clawdy desk window"
    # Longest reply line read from the daemon; anything longer is junk.
    _MAX_REPLY_BYTES = 4096
    # protocol.PERMISSION_SUMMARY_MAX and _FILE_PATH_TOOLS.
    _SUMMARY_MAX = 120
    _FILE_PATH_TOOLS = ("Edit", "Write", "Read")

    # POSIX: the Unix socket itself. Windows: the file the daemon publishes its
    # loopback port and shared secret in.
    SOCKET_PATH = os.environ.get(
        "CLAWD_TANK_SOCKET",
        str(Path.home() / ".clawd-tank"
            / ("endpoint.json" if sys.platform == "win32" else "sock")),
    )

    _CLAUDE_ARGV_RE = re.compile(r"(^|/)claude($|\\s)")

    # Windows: image name of the native Claude Code install.
    _CLAUDE_EXE_NAME = "claude.exe"
    # A hook sits a handful of levels below Claude (python launcher, python, one
    # to three bash.exe). Anything deeper is not this hook's Claude.
    _MAX_ANCESTRY_DEPTH = 32


    def _ps(field, pid):
        """Run `ps -o <field>= -p <pid>`, return trimmed stdout. Empty on error."""
        try:
            r = subprocess.run(
                ["ps", "-o", field + "=", "-p", str(pid)],
                capture_output=True, text=True, timeout=1.0,
            )
            return r.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            return ""


    def _walk_to_claude(start, table):
        """Return the first PID at or above `start` whose image is claude.exe.

        `table` maps pid -> (parent pid, exe name) from one Toolhelp32 snapshot.
        None when the chain breaks (parent already exited), loops (a reused
        PID), or exceeds the depth limit.

        Mirrors clawd_tank_daemon/pid_resolver.py:walk_to_claude — keep in sync.
        """
        pid = start
        seen = set()
        for _ in range(_MAX_ANCESTRY_DEPTH):
            if pid in seen or pid not in table:
                return None
            seen.add(pid)
            ppid, name = table[pid]
            if name.lower() == _CLAUDE_EXE_NAME:
                return pid
            pid = ppid
        return None


    def _windows_process_table():
        """Snapshot every process once: pid -> (parent pid, exe name)."""
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        th32cs_snapprocess = 0x00000002
        invalid_handle = wintypes.HANDLE(-1).value
        snap = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
        if not snap or snap == invalid_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        table = {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snap)
        return table


    def _find_claude_pid():
        """Walk from os.getppid() up the process tree to find the long-lived
        Claude Code PID.

        Mirrors clawd_tank_daemon/pid_resolver.py — keep in sync.

        POSIX: asks `ps` per ancestor; falls back to os.getppid() if no
        `claude` ancestor.

        Windows: walks one Toolhelp32 snapshot for a claude.exe ancestor (the
        native install). Returns None if there is none, or on any failure — never
        os.getppid(): the hook runs under a shell that exits the moment it
        returns, and sending that shell's PID would make the daemon's liveness
        checker evict a session that is very much alive. A node-hosted install
        is not recognized (that needs argv, which the snapshot lacks), so it
        falls back to the daemon's staleness timeout.
        """
        if sys.platform == "win32":
            try:
                return _walk_to_claude(os.getppid(), _windows_process_table())
            except Exception:
                return None
        start = os.getppid()
        pid = start
        while pid > 1:
            if _ps("comm", pid) == "claude":
                return pid
            if _CLAUDE_ARGV_RE.search(_ps("command", pid)):
                return pid
            ppid_str = _ps("ppid", pid)
            try:
                pid = int(ppid_str)
            except ValueError:
                break
        return start


    def _tool_summary(tool_name, tool_input):
        """Short single-line description of what a tool wants to do, for the
        permission bubble: the command for Bash, the file path for Edit/Write/Read,
        the tool name otherwise. Control characters become spaces; the result is cut
        to _SUMMARY_MAX characters with an ellipsis.

        Mirrors clawd_tank_daemon/protocol.py:permission_tool_summary - keep in sync.
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
        if len(text) > _SUMMARY_MAX:
            text = text[:_SUMMARY_MAX - 1] + "\\u2026"
        return text


    def _permission_wait_seconds():
        try:
            value = float(os.environ.get(PERMISSION_WAIT_ENV, ""))
        except ValueError:
            return PERMISSION_WAIT_SECONDS
        return value if 0 < value < float("inf") else PERMISSION_WAIT_SECONDS


    def _read_decision(sock, wait_seconds):
        """Read the daemon's one reply line and return "allow" or "deny"; None for
        anything else (no answer in time, EOF, junk, any error). Never raises and
        never returns allow unless the daemon said exactly that."""
        try:
            deadline = None if wait_seconds is None else time.monotonic() + wait_seconds
            buf = b""
            while b"\\n" not in buf:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                sock.settimeout(remaining)
                chunk = sock.recv(_MAX_REPLY_BYTES)
                if not chunk:
                    return None
                buf += chunk
                if len(buf) > _MAX_REPLY_BYTES:
                    return None
            reply = json.loads(buf.split(b"\\n", 1)[0].decode("utf-8"))
            decision = reply.get("decision") if isinstance(reply, dict) else None
            return decision if decision in ("allow", "deny") else None
        except Exception:
            return None


    def _print_decision(decision, agent):
        """Return the decision in the format expected by the calling agent.

        Kiro's PreToolUse hook uses exit status: zero allows the tool hook to
        continue, nonzero blocks the tool. Missing/late decisions fail closed
        for Kiro because Clawdy is acting as its approval gate.
        """
        if agent == "kiro":
            if decision != "allow":
                print(PERMISSION_DENY_MESSAGE, file=sys.stderr)
                sys.exit(2)
            return
        if agent == "pi":
            # Pi's extension reads {"decision": "allow|deny"} from stdout.
            if decision in ("allow", "deny"):
                sys.stdout.write(json.dumps({"decision": decision}, separators=(",", ":")) + chr(10))
                sys.stdout.flush()
            return
        if decision == "allow":
            outcome = {"behavior": "allow"}
        elif decision == "deny":
            outcome = {"behavior": "deny", "message": PERMISSION_DENY_MESSAGE}
        else:
            return
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PermissionRequest", "decision": outcome,
        }}, separators=(",", ":")) + "\\n")
        sys.stdout.flush()


    # Mirrors protocol.classify_exhaustion (this script cannot import it).
    def _classify_exhaustion(hook):
        fields = ("error", "stop_reason", "error_type", "error_details")
        text = " ".join(str(hook.get(f) or "") for f in fields).lower()
        if any(m in text for m in ("credit", "quota", "billing", "insufficient")):
            return "Out of credits"
        if any(m in text for m in ("usage limit", "usage_limit", "rate_limit")):
            return "Usage limit reached"
        return None

    # Mirrors protocol._with_agent_id: hooks fired inside a subagent carry its
    # agent_id (under the parent session_id); the main agent's never do.
    def _with_agent_id(msg, hook):
        agent_id = hook.get("agent_id")
        if agent_id:
            msg["agent_id"] = agent_id
        return msg

    def hook_to_message(hook):
        """Convert a Claude Code hook payload to a daemon message."""
        event_name = hook.get("hook_event_name", "")
        session_id = hook.get("session_id", "")
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else ""
        pid = _find_claude_pid()

        if event_name == "SessionStart":
            msg = {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
            source = hook.get("source")
            if source is not None:
                msg["source"] = source
            return msg

        if event_name == "PreToolUse":
            return _with_agent_id({"event": "tool_use", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}, hook)

        if event_name == "PostToolUse":
            return _with_agent_id({"event": "tool_done", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}, hook)

        if event_name == "PermissionRequest":
            return _with_agent_id({
                "event": "permission",
                "session_id": session_id,
                "tool_name": hook.get("tool_name", ""),
                "project": project,
                "pid": pid,
                "wait": True,
                "tool_summary": _tool_summary(hook.get("tool_name", ""), hook.get("tool_input")),
            }, hook)

        if event_name == "PostToolUseFailure":
            return _with_agent_id({"event": "tool_failed", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}, hook)

        if event_name == "PreCompact":
            return {"event": "compact", "session_id": session_id, "pid": pid}

        if event_name == "Stop":
            return {
                "event": "add",
                "hook": "Stop",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": "Esperando tu respuesta",
                "pid": pid,
            }

        if event_name == "StopFailure":
            message = hook.get("error", "") or hook.get("stop_reason", "") or "Error de API"
            exhausted = _classify_exhaustion(hook)
            msg = {
                "event": "add",
                "hook": "StopFailure",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": exhausted or message,
                "pid": pid,
            }
            if exhausted:
                msg["exhausted"] = True
            return msg

        if event_name == "Notification":
            if hook.get("notification_type") != "idle_prompt":
                return None
            return {
                "event": "add",
                "hook": "Notification",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": hook.get("message", "Esperando tu respuesta"),
                "pid": pid,
            }

        if event_name == "UserPromptSubmit":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "pid": pid}

        if event_name == "SessionEnd":
            msg = {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
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


    # Codex CLI reuses Claude's event vocabulary; only the session-id namespace,
    # a couple of tool-name aliases and the card name differ. Keep this in sync
    # with clawd_tank_daemon/codex_protocol.py.
    CODEX_SESSION_PREFIX = "codex:"
    CODEX_DISPLAY_NAME = "Codex"
    CODEX_TOOL_ALIASES = {
        "shell": "Bash",
        "apply_patch": "Write",
        "local_shell": "Bash",
        "exec_command": "Bash",
        "web_search": "WebSearch",
        "webrun": "WebSearch",
        "view_image": "Read",
    }


    def _codex_tool(raw):
        if not raw:
            return ""
        if raw.startswith("mcp__"):
            return raw
        return CODEX_TOOL_ALIASES.get(raw, raw)


    def codex_hook_to_message(hook):
        """Convert a Codex CLI hook payload to a daemon message (namespaced)."""
        event_name = hook.get("hook_event_name", "")
        raw_sid = hook.get("session_id", "")
        session_id = (CODEX_SESSION_PREFIX + raw_sid) if raw_sid else raw_sid
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else ""
        pid = None  # Codex has no claude.exe-style long-lived PID to resolve.

        if event_name == "SessionStart":
            msg = {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
            source = hook.get("source") or hook.get("matcher")
            if source is not None:
                msg["source"] = source
            return msg
        if event_name == "PreToolUse":
            return {"event": "tool_use", "session_id": session_id, "tool_name": _codex_tool(hook.get("tool_name", "")), "project": project, "pid": pid}
        if event_name == "PostToolUse":
            return {"event": "tool_done", "session_id": session_id, "tool_name": _codex_tool(hook.get("tool_name", "")), "project": project, "pid": pid}
        if event_name == "PermissionRequest":
            tool_name = _codex_tool(hook.get("tool_name", ""))
            return {
                "event": "permission", "session_id": session_id,
                "tool_name": tool_name, "project": project, "pid": pid,
                "wait": True,
                "tool_summary": _tool_summary(tool_name, hook.get("tool_input")),
            }
        if event_name == "PreCompact":
            return {"event": "compact", "session_id": session_id, "pid": pid}
        if event_name == "Stop":
            return {"event": "add", "hook": "Stop", "session_id": session_id, "project": CODEX_DISPLAY_NAME, "message": "Esperando tu respuesta", "pid": pid}
        if event_name == "UserPromptSubmit":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "pid": pid}
        if event_name == "SessionEnd":
            msg = {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
            reason = hook.get("reason")
            if reason is not None:
                msg["reason"] = reason
            return msg
        if event_name == "SubagentStart":
            return {"event": "subagent_start", "session_id": session_id, "agent_id": hook.get("agent_id", ""), "pid": pid}
        if event_name == "SubagentStop":
            return {"event": "subagent_stop", "session_id": session_id, "agent_id": hook.get("agent_id", ""), "pid": pid}
        return None


    # Kiro IDE reuses Claude's event vocabulary (hook_event_name, session_id,
    # cwd, tool_name). Only the session-id namespace, tool-name aliases and the
    # card name differ. Kiro has no native PermissionRequest/Subagent hooks;
    # Clawdy uses PreToolUse as the desk approval gate.
    # Keep this in sync with clawd_tank_daemon/kiro_protocol.py.
    KIRO_SESSION_PREFIX = "kiro:"
    KIRO_DISPLAY_NAME = "Kiro"
    KIRO_TOOL_ALIASES = {
        "fs_write": "Write", "str_replace": "Edit", "fs_append": "Edit",
        "create_artifact": "Write", "createHook": "Write",
        "semantic_rename": "Edit", "smart_relocate": "Edit",
        "read_file": "Read", "read_code": "Read", "list_directory": "Read",
        "grep_search": "Grep", "file_search": "Glob",
        "execute_pwsh": "Bash", "control_pwsh_process": "Bash",
        "get_process_output": "Bash", "list_processes": "Bash",
        "web_fetch": "WebFetch", "remote_web_search": "WebSearch",
        "invoke_sub_agent": "Agent",
    }


    def _kiro_tool(raw):
        if not raw:
            return ""
        if raw.startswith("mcp__"):
            return raw
        if "::" in raw:
            return "mcp__" + raw.replace("::", "__")
        return KIRO_TOOL_ALIASES.get(raw, raw)


    def kiro_hook_to_message(hook):
        """Convert a Kiro IDE hook payload to a daemon message (namespaced)."""
        event_name = hook.get("hook_event_name", "")
        raw_sid = hook.get("session_id", "")
        session_id = (KIRO_SESSION_PREFIX + raw_sid) if raw_sid else raw_sid
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else ""
        pid = None  # Kiro has no claude.exe-style long-lived PID to resolve.

        if event_name == "SessionStart":
            msg = {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
            source = hook.get("source")
            if source is not None:
                msg["source"] = source
            return msg
        if event_name == "PreToolUse":
            tool_name = _kiro_tool(hook.get("tool_name", ""))
            return {
                "event": "permission", "session_id": session_id,
                "tool_name": tool_name, "project": project, "pid": pid,
                "wait": True,
                "tool_summary": _tool_summary(tool_name, hook.get("tool_input")),
            }
        if event_name == "PostToolUse":
            return {"event": "tool_done", "session_id": session_id, "tool_name": _kiro_tool(hook.get("tool_name", "")), "project": project, "pid": pid}
        if event_name == "Stop":
            return {"event": "add", "hook": "Stop", "session_id": session_id, "project": KIRO_DISPLAY_NAME, "message": "Esperando tu respuesta", "pid": pid}
        if event_name == "UserPromptSubmit":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "pid": pid}
        if event_name == "SessionEnd":
            msg = {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
            reason = hook.get("reason")
            if reason is not None:
                msg["reason"] = reason
            return msg
        return None


    # Antigravity (agy CLI + IDE): camelCase payload that does not name its
    # event, so the installed command passes it as argv[2] and main() injects it
    # as "hookEventName". Keep this in sync with
    # clawd_tank_daemon/antigravity_protocol.py.
    ANTIGRAVITY_SESSION_PREFIX = "antigravity:"
    ANTIGRAVITY_TOOL_ALIASES = {
        "view_file": "Read", "list_dir": "Read", "find_by_name": "Glob",
        "grep_search": "Grep", "write_to_file": "Write",
        "replace_file_content": "Edit", "multi_replace_file_content": "Edit",
        "run_command": "Bash", "search_web": "WebSearch",
        "read_url_content": "WebFetch", "invoke_subagent": "Agent",
        "manage_subagents": "Agent", "ask_question": "AskUserQuestion",
        "ask_permission": "AskUserQuestion",
    }


    def _antigravity_tool(raw):
        if not raw:
            return ""
        if raw.startswith("mcp__"):
            return raw
        return ANTIGRAVITY_TOOL_ALIASES.get(raw, "passthrough")


    def _antigravity_card_name(hook):
        transcript = str(hook.get("transcriptPath") or "").replace("\\\\", "/")
        if "antigravity-cli" in transcript:
            return "Antigravity CLI"
        if "antigravity-ide" in transcript:
            return "Antigravity IDE"
        return "Antigravity"


    def _antigravity_stop_project(hook, project):
        if project:
            return {"project": project}
        return {"project": _antigravity_card_name(hook), "project_fallback": True}


    def antigravity_hook_to_message(hook):
        """Convert an Antigravity hook payload to a daemon message (namespaced)."""
        event_name = hook.get("hookEventName", "")
        conversation_id = hook.get("conversationId", "")
        if not conversation_id:
            return None
        session_id = ANTIGRAVITY_SESSION_PREFIX + conversation_id
        workspaces = hook.get("workspacePaths") or []
        project = Path(workspaces[0]).name if workspaces else ""
        tool_call = hook.get("toolCall") or {}

        if event_name == "PreInvocation":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "project": project, "pid": None}
        if event_name == "PreToolUse":
            return {"event": "tool_use", "session_id": session_id, "tool_name": _antigravity_tool(tool_call.get("name", "")), "project": project, "pid": None}
        if event_name == "PostToolUse":
            kind = "tool_failed" if hook.get("error") else "tool_done"
            return {"event": kind, "session_id": session_id, "tool_name": _antigravity_tool(tool_call.get("name", "")), "project": project, "pid": None}
        if event_name == "Stop":
            error = hook.get("error") or ""
            if error or hook.get("terminationReason") == "error":
                exhausted = _classify_exhaustion(hook)
                msg = {
                    "event": "add", "hook": "StopFailure", "session_id": session_id,
                    **_antigravity_stop_project(hook, project),
                    "message": exhausted or error or "Agent error", "pid": None,
                }
                if exhausted:
                    msg["exhausted"] = True
                return msg
            if hook.get("fullyIdle") is False:
                return None
            return {"event": "add", "hook": "Stop", "session_id": session_id, **_antigravity_stop_project(hook, project), "message": "Waiting for your reply", "pid": None}
        return None


    # OpenCode: the plugin shim (host/opencode-plugin/clawd-tank-opencode.js)
    # posts {type, sessionID, directory, tool, args}. Keep this in sync with
    # clawd_tank_daemon/opencode_protocol.py.
    OPENCODE_SESSION_PREFIX = "opencode:"


    def _opencode_tool(raw):
        if not raw:
            return ""
        if raw.startswith("mcp__"):
            return raw
        return "passthrough"


    def opencode_hook_to_message(hook):
        """Convert an OpenCode plugin payload to a daemon message (namespaced)."""
        event_type = hook.get("type", "")
        raw_sid = hook.get("sessionID", "") or hook.get("session_id", "")
        if not raw_sid:
            return None
        session_id = OPENCODE_SESSION_PREFIX + raw_sid
        directory = hook.get("directory", "") or hook.get("cwd", "")
        project = Path(directory).name if directory else ""
        pid = None

        if event_type == "session.created":
            return {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
        if event_type == "chat.message":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "project": project, "pid": pid}
        if event_type == "session.heartbeat":
            state = hook.get("state", "registered")
            if state not in ("registered", "thinking", "working", "waiting"):
                return None
            return {"event": "session_heartbeat", "session_id": session_id, "project": project, "state": state, "tool_name": _opencode_tool(hook.get("tool", "")), "awaiting_prompt": state == "waiting", "pid": pid}
        if event_type == "session.idle":
            return {"event": "add", "hook": "Stop", "session_id": session_id, "project": project, "pid": pid, "message": "Esperando tu respuesta"}
        if event_type == "session.deleted":
            return {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
        if event_type == "tool.execute.before":
            return {"event": "tool_use", "session_id": session_id, "tool_name": _opencode_tool(hook.get("tool", "")), "project": project, "pid": pid}
        if event_type == "tool.execute.after":
            return {"event": "tool_done", "session_id": session_id, "tool_name": _opencode_tool(hook.get("tool", "")), "project": project, "pid": pid}
        if event_type == "permission.ask":
            tool_name = _opencode_tool(hook.get("tool", ""))
            return {
                "event": "permission", "session_id": session_id,
                "tool_name": tool_name, "project": project, "pid": pid,
                "wait": True,
                "tool_summary": _tool_summary(tool_name, hook.get("args")),
            }
        if event_type == "experimental.session.compacting":
            return {"event": "compact", "session_id": session_id, "pid": pid}
        return None


    # Pi (gentle-shell) extension: the shim posts {type, sessionID, directory, tool, args}.
    # Keep this in sync with clawd_tank_daemon/pi_protocol.py.
    PI_SESSION_PREFIX = "pi:"


    def _pi_tool(raw):
        if not raw:
            return ""
        if raw.startswith("mcp__"):
            return raw
        return "passthrough"


    def pi_hook_to_message(hook):
        # Convert a Pi extension payload to a namespaced daemon message.
        event_type = hook.get("type", "")
        raw_sid = hook.get("sessionID", "") or hook.get("session_id", "")
        if not raw_sid:
            return None
        session_id = PI_SESSION_PREFIX + raw_sid
        directory = hook.get("directory", "") or hook.get("cwd", "")
        project = Path(directory).name if directory else ""
        pid = None

        if event_type == "session_start":
            return {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
        if event_type == "agent_start":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "project": project, "pid": pid}
        if event_type == "turn_end":
            return {"event": "add", "hook": "Stop", "session_id": session_id, "project": project, "pid": pid, "message": "Esperando tu respuesta"}
        if event_type == "session_shutdown":
            return {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
        if event_type == "tool_call":
            return {"event": "tool_use", "session_id": session_id, "tool_name": _pi_tool(hook.get("tool", "")), "project": project, "pid": pid}
        if event_type == "tool_result":
            return {"event": "tool_done", "session_id": session_id, "tool_name": _pi_tool(hook.get("tool", "")), "project": project, "pid": pid}
        if event_type == "permission":
            raw_tool = hook.get("tool", "")
            # _tool_summary matches Claude's capitalized names, so map Pi's bash to Bash.
            summary_name = "Bash" if raw_tool == "bash" else raw_tool
            return {
                "event": "permission", "session_id": session_id,
                "tool_name": _pi_tool(raw_tool), "project": project, "pid": pid,
                "wait": True,
                "tool_summary": _tool_summary(summary_name, hook.get("args")),
            }
        return None


    _AGENT_TRANSLATORS = {
        "codex": codex_hook_to_message,
        "kiro": kiro_hook_to_message,
        "antigravity": antigravity_hook_to_message,
        "opencode": opencode_hook_to_message,
        "pi": pi_hook_to_message,
    }


    _ALLOW_SENT = False


    def _write_allow():
        """Answer an Antigravity PreToolUse gate: let the agent carry on. Written
        at most once."""
        global _ALLOW_SENT
        if _ALLOW_SENT:
            return
        _ALLOW_SENT = True
        try:
            sys.stdout.write('{"decision":"allow"}\\n')
            sys.stdout.flush()
        except Exception:
            pass


    def _send_message(msg):
        """Fire-and-forget delivery of one message (no reply is awaited)."""
        if sys.platform == "win32":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(3.0)
            if sys.platform == "win32":
                with open(SOCKET_PATH, encoding="utf-8") as f:
                    endpoint = json.load(f)
                sock.connect(("127.0.0.1", endpoint["port"]))
                sock.sendall(endpoint["token"].encode("utf-8") + b"\\n")
            else:
                sock.connect(SOCKET_PATH)
            sock.sendall(json.dumps(msg).encode("utf-8") + b"\\n")
        finally:
            sock.close()


    def _main_antigravity(event):
        """Antigravity hook entry: `<notify> antigravity <Event>`. PreToolUse is
        a gating hook, so this always answers {"decision":"allow"} (it only
        observes; it must never block the agent) and always exits 0, whatever
        goes wrong (daemon down, junk stdin, an unexpected error)."""
        gate = event == "PreToolUse"
        try:
            raw = sys.stdin.read()
            payload = json.loads(raw) if raw.strip() else None
            if gate:
                _write_allow()
            if isinstance(payload, dict):
                if event:
                    payload.setdefault("hookEventName", event)
                msg = antigravity_hook_to_message(payload)
                if msg is not None:
                    _send_message(msg)
        except BaseException:
            pass
        finally:
            if gate:
                _write_allow()
        sys.exit(0)


    def main():
        # The agent is the first CLI arg ("codex"/"kiro"); default is Claude Code.
        agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
        if agent == "antigravity":
            _main_antigravity(sys.argv[2] if len(sys.argv) > 2 else "")
        try:
            raw = sys.stdin.read()
            if not raw.strip():
                sys.exit(0)
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # A hook whose stdin is not JSON has nothing to forward. Exit 0 (silent)
            # rather than 1: this is a fire-and-forget notifier, and a non-zero exit
            # makes Codex report "Hook failed, exited with code 1" for no benefit.
            sys.exit(0)

        translator = _AGENT_TRANSLATORS.get(agent, hook_to_message)
        msg = translator(payload)
        if msg is None:
            sys.exit(0)

        # A message that asks to wait keeps its connection open for the reply.
        wait = msg.get("wait") is True
        decision = None

        # Windows has no AF_UNIX: connect to the loopback port the daemon
        # published and present its shared secret as the first line.
        if sys.platform == "win32":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(3.0)
            if sys.platform == "win32":
                with open(SOCKET_PATH, encoding="utf-8") as f:
                    endpoint = json.load(f)
                sock.connect(("127.0.0.1", endpoint["port"]))
                sock.sendall(endpoint["token"].encode("utf-8") + b"\\n")
            else:
                sock.connect(SOCKET_PATH)
            sock.sendall(json.dumps(msg).encode("utf-8") + b"\\n")
            if wait:
                decision = _read_decision(sock, _permission_wait_seconds())
        # The last two cover a torn or stale endpoint file and can only be
        # raised on the Windows branch, so POSIX behaviour is unchanged.
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout,
                json.JSONDecodeError, KeyError):
            if wait and agent == "kiro":
                _print_decision(None, agent)
            sys.exit(0)
        except Exception:
            # A waiting hook must never fail loudly or allow anything: Claude
            # Code then asks in the terminal. Other messages keep raising.
            if wait:
                if agent == "kiro":
                    _print_decision(None, agent)
                sys.exit(0)
            raise
        finally:
            sock.close()
        _print_decision(decision, agent)


    if __name__ == "__main__":
        main()
''').replace("__DISPLAY_NAME__", repr(DISPLAY_NAME))

# The statusLine bridge for Windows (STATUSLINE_BRIDGE_SH below is the POSIX one):
# stdlib-only Python, installed as statusline_bridge.py and frozen into
# margarita-statusline.exe by the PyInstaller build (see host/windows/margarita_tank.spec).
STATUSLINE_BRIDGE_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """statusline_bridge - Claude Code statusLine wrapper for Clawd Tank.

    Claude Code pipes a JSON document (including rate_limits) to the statusLine
    command on every refresh. This script caches that JSON for the daemon's usage
    bar, then chains the user's original statusLine command (saved at install time)
    with the same stdin and prints its output, so their status line keeps working.
    It must never fail loudly: every error is swallowed and the exit code is 0.
    No external dependencies.
    """
    # STATUSLINE_BRIDGE_VERSION: 1

    import json
    import ntpath
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    CLAWD_DIR = Path(os.environ.get("CLAWD_TANK_DIR") or (Path.home() / ".clawd-tank"))
    CACHE_PATH = CLAWD_DIR / "statusline-cache.json"
    STATE_PATH = CLAWD_DIR / "statusline-original.json"
    GUARD_ENV = "CLAWD_TANK_STATUSLINE_BRIDGE"
    GIT_BASH_ENV = "CLAUDE_CODE_GIT_BASH_PATH"
    CHAIN_TIMEOUT_S = 10


    def write_cache(raw):
        try:
            if not isinstance(json.loads(raw.decode("utf-8-sig")), dict):
                return
            CLAWD_DIR.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(CLAWD_DIR), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(raw)
                os.replace(tmp, CACHE_PATH)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception:
            pass


    def original_command():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
            command = state["statusLine"]["command"]
            return command if isinstance(command, str) and command.strip() else None
        except Exception:
            return None


    def _is_absolute(path):
        # A drive (or UNC share) AND a root: "C:foo" and "\\\\foo" resolve against
        # the current directory or drive, which is where a project can plant files.
        drive, rest = ntpath.splitdrive(path)
        return bool(drive) and rest[:1] in ("\\\\", "/")

    def _same_path(a, b):
        return ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b))

    def _trusted_path_dirs(environ, cwd):
        """Absolute PATH entries that are not the current directory, in order.
        The bridge runs in the user's project: shutil.which on Windows also looks
        in the cwd (and an empty or relative entry means the cwd), so a repository
        could plant its own git.exe there and have it executed."""
        raw = next((v for k, v in environ.items() if k.upper() == "PATH"), "") or ""
        for entry in raw.split(";"):
            entry = entry.strip().strip('"')
            if entry and _is_absolute(entry) and not _same_path(entry, cwd):
                yield entry

    # Where bash.exe sits relative to the folder holding git.exe, by that folder's
    # name: Git for Windows has git.exe in cmd, mingw64/bin or bin (bash.exe is
    # in the install's bin folder, or next to git.exe when that is bin itself).
    def _bash_folder(git_dir):
        name = ntpath.basename(git_dir).lower()
        if name == "cmd":
            return ntpath.join(git_dir, "..", "bin")
        if name == "bin":
            parent = ntpath.basename(ntpath.dirname(git_dir)).lower()
            if parent in ("mingw64", "mingw32", "clangarm64"):
                return ntpath.join(git_dir, "..", "..", "bin")
            return git_dir
        return None

    def _is_bash_exe(path, isfile):
        return (isinstance(path, str) and _is_absolute(path)
                and ntpath.basename(path).lower() == "bash.exe" and isfile(path))

    def find_git_bash(environ, isfile, cwd):
        """The Git Bash that Claude Code runs statusLine commands through on Windows:
        the one named by CLAUDE_CODE_GIT_BASH_PATH (an absolute path to an existing
        bash.exe), else the bash.exe of the Git for Windows install whose git.exe is
        on PATH. git is looked up only in absolute PATH entries other than `cwd`,
        never through shutil.which (it searches the cwd). Never a bash found on PATH
        itself: System32/bash.exe is the WSL launcher and would run the command in
        Linux. None when there is no Git Bash."""
        configured = environ.get(GIT_BASH_ENV)
        if configured and _is_bash_exe(configured, isfile):
            return configured
        for directory in _trusted_path_dirs(environ, cwd):
            if not isfile(ntpath.join(directory, "git.exe")):
                continue
            folder = _bash_folder(directory)
            if folder is None:
                continue
            candidate = ntpath.normpath(ntpath.join(folder, "bash.exe"))
            if _is_bash_exe(candidate, isfile):
                return candidate
        return None


    def chain_invocation(command, platform=None, environ=None, isfile=None, cwd=None):
        """(args, shell) for subprocess.run to chain `command` through.

        The user's original was written for the shell Claude Code runs it with. On
        Windows that is Git Bash, not cmd.exe, so use it ([bash, "-c", command]);
        cmd.exe (shell=True) is only the fallback when no Git Bash is found.
        Elsewhere shell=True is /bin/sh, which is what Claude Code uses too."""
        if (sys.platform if platform is None else platform) == "win32":
            bash = find_git_bash(
                os.environ if environ is None else environ,
                os.path.isfile if isfile is None else isfile,
                os.getcwd() if cwd is None else cwd,
            )
            if bash:
                return [bash, "-c", command], False
        return command, True


    def chain(command, raw):
        # A bridge that finds itself as the "original" would fork forever.
        if os.environ.get(GUARD_ENV):
            return
        try:
            args, shell = chain_invocation(command)
            proc = subprocess.run(
                args, shell=shell, input=raw, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=CHAIN_TIMEOUT_S,
                env={**os.environ, GUARD_ENV: "1"},
                # pythonw has no console: without this, bash.exe gets a fresh
                # one that Windows Terminal (default terminal) opens as a tab.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            sys.stdout.buffer.write(proc.stdout)
            sys.stdout.buffer.flush()
        except Exception:
            pass


    def main():
        try:
            raw = sys.stdin.buffer.read()
        except Exception:
            raw = b""
        write_cache(raw)
        command = original_command()
        if command:
            chain(command, raw)


    if __name__ == "__main__":
        try:
            main()
        except Exception:
            pass
        sys.exit(0)
''')


# The same bridge for macOS and Linux, in plain POSIX sh. The Python one above
# needs a working python3, and a Mac may have none (or only the Xcode command
# line tools stub): a statusLine that cannot start would take the user's own
# status line down with it. Windows keeps the Python bridge (margarita-statusline.exe).
STATUSLINE_BRIDGE_SH = textwrap.dedent('''\
    #!/bin/sh
    # statusline_bridge - Claude Code statusLine wrapper for Clawd Tank (macOS, Linux).
    #
    # Claude Code pipes a JSON document (including rate_limits) to the statusLine
    # command on every refresh. This script caches that JSON for the daemon's usage
    # bar, then runs the user's original statusLine command (saved verbatim by the
    # installer in statusline-original.txt) with the same stdin and prints its
    # output, so their status line keeps working.
    #
    # POSIX sh plus cat, mkdir, mv, rm and sleep: no Python and no jq. It must never
    # fail loudly: stderr is discarded and the exit code is always 0.
    #
    # Limits: the original is stopped with SIGTERM after CLAWD_TANK_STATUSLINE_TIMEOUT
    # seconds (default 10), together with its direct children when pgrep exists; a
    # deeper process tree can outlive it. The input is held in a shell variable, so
    # NUL bytes are dropped (a JSON document has none).
    # STATUSLINE_BRIDGE_VERSION: 1

    exec 2>/dev/null

    DIR=${CLAWD_TANK_DIR:-${HOME:+$HOME/.clawd-tank}}
    CACHE="$DIR/statusline-cache.json"
    SAVED="$DIR/statusline-original.txt"
    TIMEOUT=${CLAWD_TANK_STATUSLINE_TIMEOUT:-10}
    case $TIMEOUT in ''|.|*[!0-9.]*) TIMEOUT=10 ;; esac

    # Everything Claude Code sent, byte for byte (the x keeps the trailing newlines).
    INPUT=$(cat; printf x)
    INPUT=${INPUT%x}

    write_cache() {
        [ -n "$DIR" ] || return 0
        # Only a JSON object is cached: its first non-blank character is a brace.
        lead=${INPUT%%[![:space:]]*}
        case ${INPUT#"$lead"} in '{'*) ;; *) return 0 ;; esac
        [ ! -d "$CACHE" ] || return 0
        mkdir -p "$DIR" || return 0
        tmp="$CACHE.$$.tmp"
        # A temp file in the same folder and mv replace the cache atomically; the
        # umask keeps it private to the user.
        if ( umask 077 && printf '%s' "$INPUT" >"$tmp" ) && mv -f "$tmp" "$CACHE"; then
            :
        else
            rm -f "$tmp"
        fi
    }

    run_original() {
        # The payload arrives on stdin; a background job would get /dev/null.
        exec 3<&0
        CLAWD_TANK_STATUSLINE_BRIDGE=1 /bin/sh -c "$COMMAND" <&3 3<&- &
        child=$!
        (
            trap 'kill "$sleeper"; exit 0' TERM
            sleep "$TIMEOUT" &
            sleeper=$!
            wait "$sleeper"
            # Note the children first: once the parent dies they are re-parented.
            kids=$(pgrep -P "$child")
            kill "$child" $kids
        ) >/dev/null 2>&1 3<&- </dev/null &
        watchdog=$!
        wait "$child"
        kill "$watchdog"
    }

    write_cache

    # A bridge that finds itself as the "original" would fork forever.
    [ -z "$CLAWD_TANK_STATUSLINE_BRIDGE" ] || exit 0
    [ -n "$DIR" ] && [ -r "$SAVED" ] || exit 0
    COMMAND=$(cat "$SAVED")
    case $COMMAND in *[![:space:]]*) ;; *) exit 0 ;; esac
    printf '%s' "$INPUT" | run_original
    exit 0
''')

# File name of the console-subsystem notify exe that the Windows PyInstaller
# build ships next to the tray exe (see host/windows/margarita_tank.spec).
NOTIFY_EXE_NAME = "margarita-notify.exe"


def build_hook_command(platform: str, frozen: bool, executable: str, script_path) -> str:
    """The command Claude Code runs for every hook.

    POSIX runs the script directly through its shebang. Windows has no shebang
    support, so the interpreter is named explicitly. A .cmd shim would work too,
    but it puts a second process between Claude Code and the hook on the hot
    path of every event, for nothing.

    A packaged Windows build (PyInstaller sets sys.frozen) has no Python
    interpreter to name: sys.executable is the tray app itself, so naming it
    would start another tray instance on every hook. It runs the bundled
    console notify exe that sits next to the tray exe instead.

    Windows paths are quoted because they may contain spaces; Claude Code hands
    the command to `cmd.exe /d /s /c "<command>"`, which strips only the outer
    pair and passes the rest through verbatim.
    """
    if platform == "win32":
        if frozen:
            notify_exe = ntpath.join(ntpath.dirname(executable), NOTIFY_EXE_NAME)
            return f'"{notify_exe}"'
        # The tray may run under pythonw, whose stdin/stdout are None. Hooks
        # read a JSON payload from stdin and permission hooks write a reply,
        # so they must use the console interpreter even for a hidden tray.
        if ntpath.basename(executable).lower() == "pythonw.exe":
            executable = ntpath.join(ntpath.dirname(executable), "python.exe")
        return f'"{executable}" "{script_path}"'
    return str(script_path)


HOOK_EXE_DIR_ENV = "CLAWD_TANK_HOOK_EXE_DIR"


def resolve_hook_executable(platform: str, frozen: bool, executable: str, env) -> str:
    """The executable the hook builders derive commands from.

    Normally `executable` itself. A frozen Windows build whose daemon lives in
    another folder may name the folder holding margarita-notify.exe and
    margarita-statusline.exe through CLAWD_TANK_HOOK_EXE_DIR. The directory is
    composed into a cmd.exe line, so it must be absolute, contain both exes and
    have no double quote; anything else is ignored with a warning.
    """
    override = env.get(HOOK_EXE_DIR_ENV)
    if not override or platform != "win32" or not frozen:
        return executable
    ok = (
        ntpath.isabs(override)
        and bool(ntpath.splitdrive(override)[0])
        and '"' not in override
        and all(os.path.isfile(ntpath.join(override, n)) for n in (NOTIFY_EXE_NAME, STATUSLINE_EXE_NAME))
    )
    if not ok:
        logger.warning("Ignoring invalid %s=%r", HOOK_EXE_DIR_ENV, override)
        return executable
    return ntpath.join(override, NOTIFY_EXE_NAME)


_HOOK_EXECUTABLE = resolve_hook_executable(
    sys.platform, getattr(sys, "frozen", False), sys.executable, os.environ
)

HOOK_COMMAND = build_hook_command(
    sys.platform, getattr(sys, "frozen", False), _HOOK_EXECUTABLE, NOTIFY_SCRIPT_PATH
)


def build_statusline_script(platform: str) -> str:
    """The bridge script to install on `platform`: Windows keeps the Python one
    (also frozen into margarita-statusline.exe), everywhere else it is plain sh,
    so the user's statusLine never depends on a working python3."""
    return STATUSLINE_BRIDGE_SCRIPT if platform == "win32" else STATUSLINE_BRIDGE_SH


def build_statusline_command(platform: str, frozen: bool, executable: str, script_path) -> str:
    """The statusLine command that runs the bridge on `platform`.

    POSIX runs the sh script through /bin/sh, so it works even if the file lost
    its execute bit (the path is shell-quoted: this is a shell command line that
    may sit under a home directory with spaces). Windows names the interpreter,
    like build_hook_command(), or runs the bundled console exe when frozen.
    """
    if platform == "win32":
        if frozen:
            exe = ntpath.join(ntpath.dirname(executable), STATUSLINE_EXE_NAME)
            return f'"{exe}"'
        return f'"{executable}" "{script_path}"'
    return "/bin/sh " + shlex.quote(str(script_path))


STATUSLINE_COMMAND = build_statusline_command(
    sys.platform, getattr(sys, "frozen", False), _HOOK_EXECUTABLE, STATUSLINE_SCRIPT_PATH
)


def build_hooks_config(command: str) -> dict:
    """Every managed hook group, each running `command`."""
    return {
        "SessionStart": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "StopFailure": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "Notification": [
            {
                "matcher": "idle_prompt",
                "hooks": [{"type": "command", "command": command}],
            }
        ],
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        # Scoped to AskUserQuestion only: the sole purpose is clearing the "waiting
        # for input" alert when the user answers. Registering PostToolUse for every
        # tool would double the device's event/BLE traffic for no added value.
        "PostToolUse": [
            {
                "matcher": ASK_USER_QUESTION_TOOL,
                "hooks": [{"type": "command", "command": command}],
            }
        ],
        # Claude is blocked waiting for the user to approve a tool → waiting/alert.
        "PermissionRequest": [
            {"hooks": [{
                "type": "command",
                "command": command,
                "timeout": PERMISSION_HOOK_TIMEOUT_SECONDS,
            }]}
        ],
        # A tool genuinely errored (not a non-zero shell exit) → confused.
        "PostToolUseFailure": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "PreCompact": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SubagentStart": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SubagentStop": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
    }


HOOKS_CONFIG = build_hooks_config(HOOK_COMMAND)


# --- Codex CLI hooks ----------------------------------------------------------
#
# Codex reuses Claude's event vocabulary, so the SAME notify script handles it;
# the trailing " codex" argument tells the script to use the Codex translator
# (namespaced session ids + tool aliases). Config lives in ~/.codex/hooks.json,
# a first-class Codex hook source that is plain JSON — so we edit it with the
# same ownership discipline as ~/.claude/settings.json rather than rewriting the
# user's config.toml (which we never touch).
CODEX_HOOKS_PATH = Path.home() / ".codex" / "hooks.json"


def build_codex_hook_command(platform: str, frozen: bool, executable, script_path) -> str:
    """The Codex hook command. Codex on Windows runs hooks through `cmd /c` or
    `powershell -Command`, and both exit 1 on the double-quoted form that
    build_hook_command produces, so paths WITHOUT whitespace go unquoted. Paths
    with whitespace keep the quoted form (known limitation: Codex fails them)."""
    if platform == "win32":
        if frozen:
            target = ntpath.join(ntpath.dirname(executable), NOTIFY_EXE_NAME)
            parts = [str(target)]
        else:
            if ntpath.basename(str(executable)).lower() == "pythonw.exe":
                executable = ntpath.join(ntpath.dirname(str(executable)), "python.exe")
            parts = [str(executable), str(script_path)]
        if not any(c.isspace() for p in parts for c in p):
            return " ".join(parts) + " codex"
    return build_hook_command(platform, frozen, executable, script_path) + " codex"


CODEX_HOOK_COMMAND = build_codex_hook_command(
    sys.platform, getattr(sys, "frozen", False), _HOOK_EXECUTABLE, NOTIFY_SCRIPT_PATH
)


def build_codex_hooks_config(command: str) -> dict:
    """Codex hook groups, keyed by Codex lifecycle event. Codex matches tools with
    a regex matcher; a group with no matcher fires on every occurrence of the
    event. Mirrors the Claude set minus events Codex does not emit (StopFailure,
    PostToolUseFailure); PostToolUse is scoped to the question tool like Claude."""
    return {
        "SessionStart": [{"hooks": [{"type": "command", "command": command}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": command}]}],
        "PreToolUse": [{"hooks": [{"type": "command", "command": command}]}],
        "PostToolUse": [
            {"matcher": ASK_USER_QUESTION_TOOL, "hooks": [{"type": "command", "command": command}]}
        ],
        "PermissionRequest": [{"hooks": [{
            "type": "command", "command": command,
            "timeout": PERMISSION_HOOK_TIMEOUT_SECONDS,
            "statusMessage": "Waiting for Clawdy pet approval",
        }]}],
        "PreCompact": [{"hooks": [{"type": "command", "command": command}]}],
        "Stop": [{"hooks": [{"type": "command", "command": command}]}],
        "SessionEnd": [{"hooks": [{"type": "command", "command": command}]}],
        "SubagentStart": [{"hooks": [{"type": "command", "command": command}]}],
        "SubagentStop": [{"hooks": [{"type": "command", "command": command}]}],
    }


CODEX_HOOKS_CONFIG = build_codex_hooks_config(CODEX_HOOK_COMMAND)


def _load_codex_hooks() -> dict | None:
    """Parse ~/.codex/hooks.json. Returns {} when absent/empty, None when it
    exists but is not a readable JSON object (so we leave it untouched)."""
    if not CODEX_HOOKS_PATH.exists():
        return {}
    try:
        text = CODEX_HOOKS_PATH.read_text(encoding="utf-8-sig")
        if not text.strip():
            return {}
        data = json.loads(text)
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def install_codex_hooks() -> bool:
    """Merge our Codex hook groups into ~/.codex/hooks.json without clobbering the
    user's own hooks, using the same ownership rule as the Claude installer:
    prune only groups whose every command is ours, then append ours where absent.
    The top-level "hooks" object holds the per-event groups (Codex's hooks.json
    shape). Returns False, leaving the file untouched, when it cannot be parsed."""
    CODEX_HOOKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _load_codex_hooks()
    if data is None:
        logger.warning("Not installing Codex hooks: %s is not readable JSON; left untouched", CODEX_HOOKS_PATH)
        return False

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    for event_name, our_entries in CODEX_HOOKS_CONFIG.items():
        existing = hooks.get(event_name)
        if not isinstance(existing, list):
            existing = []
        kept = [g for g in existing if not _is_our_managed_group(g)]
        for our_entry in our_entries:
            if not _our_hook_present(kept, _matcher_of(our_entry)):
                kept.append(copy.deepcopy(our_entry))
        hooks[event_name] = kept

    _write_json_atomic(CODEX_HOOKS_PATH, data)
    logger.info("Installed Codex hooks in %s", CODEX_HOOKS_PATH)
    return True


def uninstall_codex_hooks() -> bool:
    """Remove our Codex hook groups from ~/.codex/hooks.json, with the same
    ownership rule install uses: drop only groups that are purely ours, delete an
    event list when emptied, and the "hooks" object when it empties. Idempotent;
    the file is not rewritten when nothing of ours is in it. Returns True when no
    hook of ours remains (including when the file is absent)."""
    if not CODEX_HOOKS_PATH.exists():
        return True
    data = _load_codex_hooks()
    if data is None:
        logger.warning("Not uninstalling Codex hooks: %s is not readable JSON; left untouched", CODEX_HOOKS_PATH)
        return False

    hooks = data.get("hooks")
    changed = False
    if isinstance(hooks, dict):
        for event_name, groups in list(hooks.items()):
            if not isinstance(groups, list):
                continue
            kept = [g for g in groups if not _is_our_managed_group(g)]
            if len(kept) == len(groups):
                continue
            changed = True
            if kept:
                hooks[event_name] = kept
            else:
                del hooks[event_name]
        if changed and not hooks:
            del data["hooks"]

    if not changed:
        return True
    _write_json_atomic(CODEX_HOOKS_PATH, data)
    logger.info("Uninstalled Codex hooks from %s", CODEX_HOOKS_PATH)
    return True


# --- Kiro IDE / Kiro CLI hooks ------------------------------------------------
#
# Kiro reuses Claude's event vocabulary and the SAME notify script handles it;
# the trailing " kiro" argument selects the Kiro translator (namespaced session
# ids + Kiro tool aliases). Unlike Claude (~/.claude/settings.json) and Codex
# (~/.codex/hooks.json), Kiro Agent Hooks are discovered ONLY per workspace at
# <workspace>/.kiro/hooks/*.json — there is no global ~/.kiro/hooks yet
# (kirodotdev/Kiro#5440, #9075). So these functions take the workspace folder
# and write a single file we fully own, clawdy.json, which install overwrites and
# uninstall deletes outright — no need to merge with user hooks, since each hook
# lives in its own file. The same file is read by both the IDE and the CLI's v3
# engine (the v2 engine does not read standalone hook files).
KIRO_HOOKS_DIRNAME = ".kiro/hooks"
KIRO_HOOKS_FILENAME = "clawdy.json"
KIRO_WORKSPACES_PATH = CLAWD_DIR / "kiro-workspaces.json"
KIRO_HOOK_COMMAND = HOOK_COMMAND + " kiro"

# Kiro has no PermissionRequest trigger, so its PreToolUse hook acts as an
# explicit approval gate for each tool invocation. Other unsupported lifecycle
# hooks (StopFailure, Notification, PreCompact, Subagent) stay unregistered.
KIRO_TRIGGERS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")


def build_kiro_hooks_file(command: str) -> dict:
    """The contents of our <workspace>/.kiro/hooks/clawdy.json: one v1 hook file
    holding a command hook per Kiro trigger the daemon reacts to."""
    return {
        "version": "v1",
        "hooks": [
            {
                "name": f"Clawdy: {trigger}",
                "trigger": trigger,
                **(
                    {"timeout": PERMISSION_HOOK_TIMEOUT_SECONDS}
                    if trigger == "PreToolUse" else {}
                ),
                "action": {"type": "command", "command": command},
            }
            for trigger in KIRO_TRIGGERS
        ],
    }


def kiro_hooks_path(workspace) -> Path:
    """Path to our Kiro hook file inside `workspace`."""
    return Path(workspace) / KIRO_HOOKS_DIRNAME / KIRO_HOOKS_FILENAME


def _load_kiro_workspaces() -> list[str] | None:
    if not KIRO_WORKSPACES_PATH.exists():
        return []
    try:
        data = json.loads(KIRO_WORKSPACES_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list) or not all(isinstance(p, str) for p in data):
        return None
    return data


def _track_kiro_workspace(workspace) -> bool:
    workspaces = _load_kiro_workspaces()
    if workspaces is None:
        logger.warning("Could not track Kiro workspace: %s is not valid JSON", KIRO_WORKSPACES_PATH)
        return False
    value = str(Path(workspace).resolve())
    if value not in workspaces:
        workspaces.append(value)
    try:
        _write_json_atomic(KIRO_WORKSPACES_PATH, workspaces)
    except OSError:
        logger.warning("Could not track Kiro workspace %s", value)
        return False
    return True


def install_kiro_hooks(workspace) -> bool:
    """Write our Kiro hook file into `workspace`/.kiro/hooks/clawdy.json.

    We own the whole file, so install just (re)writes it; the user's own hooks
    live in other files and are never touched. Returns True on success, False if
    the file could not be written."""
    path = kiro_hooks_path(workspace)
    try:
        _write_json_atomic(path, build_kiro_hooks_file(KIRO_HOOK_COMMAND))
    except OSError:
        logger.warning("Could not install Kiro hooks at %s", path)
        return False
    if not _track_kiro_workspace(workspace):
        path.unlink(missing_ok=True)
        return False
    logger.info("Installed Kiro hooks: %s", path)
    return True


def are_kiro_hooks_installed(workspace) -> bool:
    """True if our Kiro hook file exists in `workspace` and carries the current
    command (so a changed interpreter/install path is treated as outdated)."""
    path = kiro_hooks_path(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    expected = build_kiro_hooks_file(KIRO_HOOK_COMMAND)
    return data == expected


def uninstall_kiro_hooks(workspace) -> bool:
    """Delete our Kiro hook file from `workspace`. We own the whole file, so this
    removes only our hooks. Idempotent; True when our file is gone (including when
    it was never there)."""
    path = kiro_hooks_path(workspace)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not uninstall Kiro hooks at %s", path)
        return False
    logger.info("Uninstalled Kiro hooks from %s", path)
    return True


def uninstall_tracked_kiro_hooks() -> bool:
    """Remove Clawdy's Kiro hook files from workspaces recorded at install."""
    workspaces = _load_kiro_workspaces()
    if workspaces is None:
        logger.warning("Not uninstalling tracked Kiro hooks: invalid workspace list")
        return False
    try:
        for workspace in workspaces:
            kiro_hooks_path(workspace).unlink(missing_ok=True)
        KIRO_WORKSPACES_PATH.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove all tracked Kiro hooks")
        return False
    return True


def install_notify_script() -> None:
    """Write the standalone notify script to NOTIFY_SCRIPT_PATH."""
    CLAWD_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFY_SCRIPT_PATH.write_text(NOTIFY_SCRIPT, encoding="utf-8")
    if sys.platform != "win32":
        # Windows has no execute bit — chmod there only toggles read-only — and
        # HOOK_COMMAND names the interpreter, so nothing needs to be executable.
        NOTIFY_SCRIPT_PATH.chmod(0o755)
    logger.info("Installed hook script: %s", NOTIFY_SCRIPT_PATH)


def install_statusline_bridge_script() -> None:
    """Write the standalone statusLine bridge to STATUSLINE_SCRIPT_PATH."""
    CLAWD_DIR.mkdir(parents=True, exist_ok=True)
    STATUSLINE_SCRIPT_PATH.write_text(build_statusline_script(sys.platform), encoding="utf-8")
    if sys.platform != "win32":
        STATUSLINE_SCRIPT_PATH.chmod(0o755)
    logger.info("Installed statusLine bridge: %s", STATUSLINE_SCRIPT_PATH)


def _statusline_state_path() -> Path:
    return CLAWD_DIR / STATUSLINE_STATE_NAME


def _statusline_command_path() -> Path:
    return CLAWD_DIR / STATUSLINE_COMMAND_NAME


def _legacy_posix_statusline_command() -> str | None:
    """The statusLine command POSIX installs wrote before the sh bridge: the
    Python script run through its shebang. None on Windows, where that script is
    still the current one."""
    if sys.platform == "win32":
        return None
    return shlex.quote(str(STATUSLINE_SCRIPT_PATH.with_name(LEGACY_STATUSLINE_SCRIPT_NAME)))


def _statusline_is_ours(value) -> bool:
    """True if a settings.statusLine value runs our bridge: the current command,
    or one left by another interpreter / install folder (same script, or the
    bundled exe) or by the python3 bridge POSIX ran before the sh one, so a
    reinstall replaces it instead of treating it as the user's own. A wrapper
    that merely mentions the script is not ours."""
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    if command == STATUSLINE_COMMAND or command.startswith(STATUSLINE_COMMAND + " "):
        return True
    legacy = _legacy_posix_statusline_command()
    if legacy and (command == legacy or command.startswith(legacy + " ")):
        return True
    script = re.escape(str(STATUSLINE_SCRIPT_PATH))
    pattern = (
        '^(?:"[^"]+" "' + script + '"'
        r'|"[^"]*[\\/](?i:' + re.escape(STATUSLINE_EXE_NAME) + ')")( |$)')
    return re.match(pattern, command) is not None


def _write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _saved_original_command() -> str | None:
    """The command of the saved original statusLine; None when there is none (or
    it has no command, like a static text line, so there is nothing to chain)."""
    try:
        state = json.loads(_statusline_state_path().read_text(encoding="utf-8-sig"))
        command = state["statusLine"]["command"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return command if isinstance(command, str) and command.strip() else None


def _sync_statusline_command_file() -> None:
    """Keep the plain-text copy of the saved command in step with the JSON state:
    the sh bridge runs exactly that text. Removed when there is no command."""
    path = _statusline_command_path()
    command = _saved_original_command()
    if command is None:
        path.unlink(missing_ok=True)
        return
    data = command.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return
    _write_bytes_atomic(path, data)


def _statusline_command_file_is_current() -> bool:
    command = _saved_original_command()
    path = _statusline_command_path()
    if command is None:
        return not path.exists()
    return path.is_file() and path.read_bytes() == command.encode("utf-8")


def _wire_statusline(settings: dict) -> None:
    """Point settings.statusLine at the bridge, saving the user's own first.

    An already-ours value is only refreshed (never saved as the "original", or
    the bridge would chain into itself). Extra keys such as `padding` carry over.
    """
    current = settings.get("statusLine")
    state_path = _statusline_state_path()
    if not _statusline_is_ours(current):
        if current is None:
            state_path.unlink(missing_ok=True)
        else:
            _write_json_atomic(state_path, {"statusLine": current})
    _sync_statusline_command_file()
    base = current if isinstance(current, dict) else {}
    settings["statusLine"] = {**base, "type": "command", "command": STATUSLINE_COMMAND}


def _unwire_statusline(settings: dict) -> bool:
    """Undo _wire_statusline() in `settings`. Returns True if settings changed. A
    statusLine that is not ours (the user replaced it after install) is left alone.

    The saved original is NOT deleted here: the caller removes it only after the
    settings file was written, so a failed write cannot lose the original."""
    state_path = _statusline_state_path()
    if not _statusline_is_ours(settings.get("statusLine")):
        return False
    original = None
    try:
        original = json.loads(state_path.read_text(encoding="utf-8-sig")).get("statusLine")
    except (OSError, ValueError, AttributeError):
        pass
    if original is None:
        del settings["statusLine"]
    else:
        settings["statusLine"] = original
    return True


def _remove_legacy_statusline_script() -> None:
    """Delete the python3 bridge an older POSIX install left behind. Only called
    once settings.json points at the sh bridge: before that, the file is what a
    still-wired statusLine runs."""
    if sys.platform == "win32":
        return
    STATUSLINE_SCRIPT_PATH.with_name(LEGACY_STATUSLINE_SCRIPT_NAME).unlink(missing_ok=True)


def _matcher_of(entry: dict):
    """Normalised matcher of a hook group. Absent/empty matcher → None.

    Claude Code treats a group with no matcher (or "") as matching everything,
    so they are equivalent for the purpose of locating "our" group.
    """
    if not isinstance(entry, dict):
        return None
    matcher = entry.get("matcher")
    return matcher if matcher else None


# The prefix match below anchors on the whole command, which is stable on POSIX
# but not on Windows: HOOK_COMMAND embeds an absolute interpreter path that a
# rebuilt venv or a moved Python changes, while the script path never moves. An
# unrecognised prior command is not pruned on reinstall, so it would linger as a
# duplicate group invoking an interpreter that is no longer there. Match on the
# script instead, anchored so only `"<interpreter>" "<script>"` with nothing in
# front of it counts — a wrapper such as `cat "<script>"` still does not.
# The packaged build's `"<install dir>\margarita-notify.exe"` is matched the same
# way, on the exe's file name, so switching between a source checkout and an
# installed build (or moving the install) replaces the previous group too.
def build_our_command_re(platform: str, script_path):
    """Pattern recognising any command of ours on `platform`. None on POSIX,
    where only the exact current command counts."""
    if platform != "win32":
        return None
    return re.compile(
        '^(?:"[^"]+" "' + re.escape(str(script_path)) + '"'
        # Unquoted forms (Codex hooks, whose paths have no whitespace).
        r'|[^\s"]+\.exe ' + re.escape(str(script_path)) +
        r'|"[^"]*[\\/](?i:' + re.escape(NOTIFY_EXE_NAME) + ')"'
        r'|[^\s"]*[\\/](?i:' + re.escape(NOTIFY_EXE_NAME) + ')'
        r')( |$)')


_OUR_COMMAND_RE = build_our_command_re(sys.platform, NOTIFY_SCRIPT_PATH)


def _command_is_ours(command) -> bool:
    """True only if a hook command actually invokes our notify script — the exact
    path, or the path followed by args. A command that merely CONTAINS the path as a
    substring (a wrapper, or `cat <path>`) is not ours."""
    if not isinstance(command, str):
        return False
    if _OUR_COMMAND_RE is not None:
        return _OUR_COMMAND_RE.match(command) is not None
    return _command_is_current(command)


def _command_is_current(command) -> bool:
    """True only if a hook command is exactly the CURRENT HOOK_COMMAND (optionally
    followed by args). On Windows _command_is_ours() also accepts commands left by
    another interpreter or install folder, so they get pruned on reinstall; those
    must not count as installed, or startup would never replace them."""
    if not isinstance(command, str):
        return False
    return command == HOOK_COMMAND or command.startswith(HOOK_COMMAND + " ")


def _group_runs_current_command(entry: dict, timeout=None) -> bool:
    """True if a hook group contains a hook that runs the current notify command.
    With `timeout`, that hook must also carry exactly that timeout, so an entry installed before the
    timeout existed counts as outdated."""
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list):
        return False
    return any(
        isinstance(h, dict)
        and _command_is_current(h.get("command", ""))
        and (timeout is None or h.get("timeout") == timeout)
        for h in hooks_list
    )


def _timeout_of(entry: dict):
    """The timeout our config puts on this group's hook, None when it sets none."""
    for h in entry.get("hooks", []):
        if isinstance(h, dict):
            return h.get("timeout")
    return None


def _is_our_managed_group(entry: dict) -> bool:
    """True if this group was created by Clawd Tank — a non-empty hooks list where
    EVERY hook runs our notify script. Such groups are safe to prune on install;
    a group the user shares with us (mixing their command with ours) is not."""
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list) or not hooks_list:
        return False
    return all(isinstance(h, dict) and _command_is_ours(h.get("command", "")) for h in hooks_list)


def _our_hook_present(existing_entries, our_matcher, timeout=None) -> bool:
    """True if some existing group with the same matcher already runs the current
    command (and, when `timeout` is given, with that timeout)."""
    if not isinstance(existing_entries, list):
        return False
    for entry in existing_entries:
        if _matcher_of(entry) == our_matcher and _group_runs_current_command(entry, timeout):
            return True
    return False


def _load_settings() -> dict | None:
    """Parse the Claude settings file. Returns {} when it does not exist and None
    when it exists but cannot be read, decoded or parsed into a JSON object.

    Read as utf-8-sig so a BOM left by a Windows editor is not treated as invalid.
    """
    if not CLAUDE_SETTINGS_PATH.exists():
        return {}
    try:
        text = CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8-sig")
        if not text.strip():
            return {}  # an empty file holds no user settings to protect
        settings = json.loads(text)
    except (ValueError, OSError):  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        return None
    return settings if isinstance(settings, dict) else None


def _write_settings_atomic(settings: dict) -> None:
    """Write via a temp file + os.replace so a crash mid-write never truncates
    the user's settings. Replaces the symlink target (not the link itself) and
    keeps the existing file's permission bits."""
    target = CLAUDE_SETTINGS_PATH.resolve()
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        if target.exists():
            os.chmod(tmp_path, stat.S_IMODE(target.stat().st_mode))
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --- Cleanup for the retired Claude terminal panel ---------------------------
# Only removal remains, so older installations stop loading our own plugin.
MOD_NAME = "margarita-band"
MOD_DIR = CLAWD_DIR / "claude-mod" / MOD_NAME
PLUGIN_DIRS_ENV = "CLAUDE_CODE_PLUGIN_DIRS"

def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write helper/plugin files atomically so readers never see partial content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise




def _is_our_mod_entry(entry: str) -> bool:
    """True if one plugin-folder entry names MOD_DIR (any spelling of the same
    folder: trailing separator, `~`, case on Windows)."""
    entry = entry.strip()
    if not entry:
        return False
    def normal(p):
        return os.path.normcase(os.path.normpath(os.path.expanduser(p)))
    return normal(entry) == normal(str(MOD_DIR))


def _plugin_dir_entries(settings: dict):
    """(env, entries): the settings `env` object and the folders listed in its
    CLAUDE_CODE_PLUGIN_DIRS. (None, None) when either has a shape we cannot
    edit safely (an `env` that is not an object, a value that is not a string)."""
    env = settings.get("env")
    if env is None:
        return {}, []
    if not isinstance(env, dict):
        return None, None
    value = env.get(PLUGIN_DIRS_ENV)
    if value is None:
        return env, []
    if not isinstance(value, str):
        return None, None
    return env, value.split(os.pathsep)


def _remove_mod_entry(settings: dict) -> bool:
    """Drop our folder from env.CLAUDE_CODE_PLUGIN_DIRS in `settings`. Returns True
    if settings changed. The user's other folders stay; the key goes when ours was
    the last one, and `env` goes only when removing the key emptied it."""
    env, entries = _plugin_dir_entries(settings)
    if not entries:
        return False
    kept = [e for e in entries if not _is_our_mod_entry(e)]
    if len(kept) == len(entries):
        return False
    kept = [e for e in kept if e.strip()]
    if kept:
        env[PLUGIN_DIRS_ENV] = os.pathsep.join(kept)
    else:
        del env[PLUGIN_DIRS_ENV]
        if not env:
            del settings["env"]
    return True


def is_mod_enabled() -> bool:
    """True if settings.json lists our mod folder in CLAUDE_CODE_PLUGIN_DIRS."""
    settings = _load_settings()
    if not settings:
        return False
    _env, entries = _plugin_dir_entries(settings)
    return any(_is_our_mod_entry(e) for e in entries or [])




def disable_mod() -> bool:
    """Remove only our folder from env.CLAUDE_CODE_PLUGIN_DIRS. The copied files
    stay where they are. Idempotent; the file is not rewritten (or created) when
    our folder is not listed.

    Returns True when our folder is no longer listed. Returns False — leaving the
    file untouched — when an existing settings file cannot be parsed."""
    if not CLAUDE_SETTINGS_PATH.exists():
        return True
    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not disabling the Claude Code mod: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False
    if _plugin_dir_entries(settings)[1] is None:
        logger.warning("Cannot clean retired mod: plugin folder configuration is invalid")
        return False
    if not _remove_mod_entry(settings):
        return True
    _write_settings_atomic(settings)
    logger.info("Disabled Claude Code mod in %s", CLAUDE_SETTINGS_PATH)
    return True


def cleanup_retired_mod() -> bool:
    """Remove the retired panel's config entry and only its installed directory."""
    if not disable_mod():
        return False
    if MOD_DIR.is_symlink():
        MOD_DIR.unlink()
    elif MOD_DIR.exists():
        target = MOD_DIR.resolve()
        if target.name != MOD_NAME or not target.is_relative_to(CLAWD_DIR.resolve()):
            raise ValueError("Retired mod directory is outside Clawdy storage")
        shutil.rmtree(MOD_DIR)
    return True




def are_hooks_installed() -> bool:
    """True only if every Clawd Tank hook (event + matcher) is already registered.

    Matcher-aware: a hook whose command is present but under the wrong matcher
    (e.g. a new matcher we started requiring) counts as NOT installed, so the
    menu bar app treats it as outdated and re-runs install_hooks().
    """
    settings = _load_settings()
    if not settings:
        return False
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    for event_name, our_entries in HOOKS_CONFIG.items():
        existing = hooks.get(event_name, [])
        expected_matchers = {_matcher_of(e) for e in our_entries}
        # (a) every expected event+matcher must be present
        for our_entry in our_entries:
            if not _our_hook_present(existing, _matcher_of(our_entry), _timeout_of(our_entry)):
                return False
        # (b) no leftover Clawd Tank group under a matcher we no longer use —
        # otherwise a superseded group would persist forever (install never re-runs).
        if isinstance(existing, list):
            for g in existing:
                if _is_our_managed_group(g) and _matcher_of(g) not in expected_matchers:
                    return False
    statusline = settings.get("statusLine")
    return (isinstance(statusline, dict)
            and statusline.get("command") == STATUSLINE_COMMAND
            and _statusline_command_file_is_current())


def install_hooks() -> bool:
    """Merge Clawd Tank hooks into Claude Code settings without clobbering the user's
    own hooks. For each managed event we drop our OWN prior groups (so a changed
    matcher self-heals instead of leaving a stale duplicate), then append the current
    config only where it isn't already present. The user's groups — and any group the
    user shares with us — are never modified or removed. Idempotent.

    Returns False — leaving the file untouched — when an existing settings file
    cannot be parsed, since rewriting it would discard the user's settings.
    """
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not installing hooks: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    for event_name, our_entries in HOOKS_CONFIG.items():
        existing = hooks.get(event_name)
        if not isinstance(existing, list):
            existing = []
        # Prune our own prior groups (self-heal across matcher/config changes); keep
        # the user's groups and any group the user shares with us untouched.
        kept = [g for g in existing if not _is_our_managed_group(g)]
        for our_entry in our_entries:
            if not _our_hook_present(kept, _matcher_of(our_entry)):
                kept.append(copy.deepcopy(our_entry))
        hooks[event_name] = kept

    _wire_statusline(settings)

    _write_settings_atomic(settings)
    _remove_legacy_statusline_script()
    logger.info("Installed hooks in %s", CLAUDE_SETTINGS_PATH)
    return True


def ensure_hooks_current(platform=None, frozen=None, executable=None) -> bool:
    """Install or re-point our Claude Code hooks when they are not current.

    Skips (returns False, settings untouched) when a frozen Windows build's
    notify exe is missing, so hooks never point at a dead executable. Returns
    True when hooks are current afterwards. Stale or moved managed hooks are
    rewritten by install_hooks(); a current install is left byte-identical.
    """
    platform = sys.platform if platform is None else platform
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = _HOOK_EXECUTABLE if executable is None else executable
    if platform == "win32" and frozen:
        notify = ntpath.join(ntpath.dirname(executable), NOTIFY_EXE_NAME)
        if not os.path.isfile(notify):
            logger.warning("Not installing hooks: %s is missing", notify)
            return False
    # The hooks name these scripts; write them first so a headless start on a
    # fresh profile never registers a hook that points at a missing file.
    install_notify_script()
    install_statusline_bridge_script()
    if are_hooks_installed():
        return True
    return install_hooks()


def uninstall_hooks() -> bool:
    """Remove every Clawd Tank hook group from Claude Code settings and restore
    the user's original statusLine (or drop ours when there was none). Our
    Claude Code mod folder is dropped from env.CLAUDE_CODE_PLUGIN_DIRS too, so
    Claude Code is not left pointing at a folder the uninstaller is removing.

    Uses the same ownership rule install_hooks() prunes with, applied to every
    event (not only those HOOKS_CONFIG lists today), so groups left by an older
    interpreter, install folder or retired event go too. The user's groups, and
    any group the user shares with us, are left exactly as they are. An event
    list is dropped only when it held nothing but our groups, and the "hooks"
    object only when removing them emptied it. Idempotent; the file is not
    rewritten when nothing of ours is in it.

    Returns True when no hook of ours remains (including when there is no
    settings file, which is left uncreated). Returns False — leaving the file
    untouched — when an existing settings file cannot be parsed.
    """
    if not CLAUDE_SETTINGS_PATH.exists():
        return True

    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not uninstalling hooks: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False

    is_unwired = _unwire_statusline(settings)
    changed = _remove_mod_entry(settings) or is_unwired

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        hooks_changed = False
        for event_name, groups in list(hooks.items()):
            if not isinstance(groups, list):
                continue
            kept = [g for g in groups if not _is_our_managed_group(g)]
            if len(kept) == len(groups):
                continue
            hooks_changed = True
            if kept:
                hooks[event_name] = kept
            else:
                del hooks[event_name]
        if hooks_changed and not hooks:
            del settings["hooks"]
        changed = changed or hooks_changed

    if not changed:
        return True

    _write_settings_atomic(settings)
    if is_unwired:
        _statusline_state_path().unlink(missing_ok=True)
        _statusline_command_path().unlink(missing_ok=True)
    logger.info("Uninstalled hooks from %s", CLAUDE_SETTINGS_PATH)
    return True


# --- OpenCode plugin installer ----------------------------------------------
#
# OpenCode is an AI coding assistant (https://opencode.ai). Unlike
# Claude Code (settings.json edits) and Codex (hooks.json edits), OpenCode is
# configured by a single opencode.json file whose `plugin` array holds file://
# URLs to plugin shims. The installer copies our plugin shim from its bundled
# source into ~/.config/opencode/plugins/clawd-tank.js on all platforms
# (or under XDG_CONFIG_HOME), and merges the
# corresponding file:// URL into the user's opencode.json plugin array.
#
# The shim source (host/opencode-plugin/clawd-tank-opencode.js) is bundled by
# setup.py / margarita_tank.spec; install_opencode_hooks() refuses (logs a
# warning) when it is not found at OPENCODE_PLUGIN_SOURCE.

OPENCODE_PLUGIN_FILENAME = "clawd-tank.js"
OPENCODE_BACKUP_SUFFIX = ".clawd-tank.bak"
_OPENCODE_BUNDLE_DIR = "opencode-plugin"


def _opencode_config_path() -> Path:
    """OpenCode uses XDG config paths on every platform, including Windows."""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "opencode" / "opencode.json"


def _opencode_plugin_path() -> Path:
    """Path the plugin shim is copied to (next to opencode.json in
    ~/.config/opencode/plugins/ on all platforms)."""
    return _opencode_config_path().parent / "plugins" / OPENCODE_PLUGIN_FILENAME


# Module-level constants — tests monkeypatch these so a tmp_path can stand in
# for the user's real ~/.config or %APPDATA%.
OPENCODE_CONFIG_PATH = _opencode_config_path()
OPENCODE_PLUGIN_PATH = _opencode_plugin_path()


def resolve_plugin_source(frozen: bool, executable: str, resourcepath, module_file) -> Path:
    """Where the bundled OpenCode plugin shim ships from.

    The shim lives at host/opencode-plugin/clawd-tank-opencode.js in the
    source tree (non-frozen runs resolve relative to host/); the macOS py2app bundle places it under
    Contents/Resources/opencode-plugin/, and the PyInstaller onedir build
    places it next to the exe. Uses the standard bundled-resource lookup so the
    installer reads the same shape regardless of platform.

    Returns the expected path even if the file is missing.
    """
    if frozen:
        base = Path(resourcepath) if resourcepath else Path(executable).parent
    else:
        base = Path(module_file).parents[1]  # host/ (hooks.py is in host/clawd_tank_menubar/)
    return base / _OPENCODE_BUNDLE_DIR / "clawd-tank-opencode.js"


# Resolved at import time; tests monkeypatch this constant.
OPENCODE_PLUGIN_SOURCE = resolve_plugin_source(
    bool(getattr(sys, "frozen", False)),
    sys.executable,
    os.environ.get("RESOURCEPATH"),
    Path(__file__).resolve(),
)


def _opencode_command_path() -> Path:
    """Where the installer leaves the notify command line for the shim."""
    return OPENCODE_PLUGIN_PATH.with_name("clawd-tank.command")


def _opencode_plugin_entry() -> str:
    """The `file://` URL OpenCode's loader expects for a local plugin file.

    PosixPath.as_uri() returns ``file:///abs/path`` on POSIX and
    ``file:///C:/abs/path`` on Windows, both of which OpenCode accepts.
    """
    return OPENCODE_PLUGIN_PATH.resolve().as_uri()


def _is_our_opencode_plugin(entry) -> bool:
    """True if a `plugin` array entry is one we wrote (the install target's
    `file://` URL, with case-folding on Windows and trailing-separator
    tolerance)."""
    if not isinstance(entry, str):
        return False
    def normal(p: str) -> str:
        return os.path.normcase(os.path.normpath(p))
    return normal(entry) == normal(_opencode_plugin_entry())


def _load_opencode_config() -> dict | None:
    """Parse opencode.json. Returns {} when absent or empty, None when present
    but not a readable JSON object (so we leave it untouched, same rule as
    Codex)."""
    if not OPENCODE_CONFIG_PATH.exists():
        return {}
    try:
        text = OPENCODE_CONFIG_PATH.read_text(encoding="utf-8-sig")
        if not text.strip():
            return {}
        data = json.loads(text)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def install_opencode_hooks() -> bool:
    """Install the OpenCode plugin shim and register it in opencode.json.

    Copies the bundled plugin source (OPENCODE_PLUGIN_SOURCE) to
    OPENCODE_PLUGIN_PATH and merges the file:// URL into the user's `plugin`
    array. If the bundled source is missing this returns False and leaves
    opencode.json untouched.

    Returns False, leaving opencode.json untouched, when the file cannot be
    parsed or the bundled plugin source is missing.
    """
    if not OPENCODE_PLUGIN_SOURCE.is_file():
        logger.warning(
            "Not installing OpenCode plugin: bundled source %s not found "
            "(see resolve_plugin_source in hooks.py)",
            OPENCODE_PLUGIN_SOURCE,
        )
        return False

    OPENCODE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _load_opencode_config()
    if data is None:
        logger.warning(
            "Not installing OpenCode plugin: %s is not a readable JSON object; "
            "left untouched",
            OPENCODE_CONFIG_PATH,
        )
        return False

    # Backup the existing config before we touch it; uninstall restores from
    # this file byte-for-byte. _write_json_atomic replaces the config on
    # success, so the backup lives alongside.
    if OPENCODE_CONFIG_PATH.exists():
        backup = OPENCODE_CONFIG_PATH.with_name(
            OPENCODE_CONFIG_PATH.name + OPENCODE_BACKUP_SUFFIX
        )
        if not backup.exists():
            backup.write_bytes(OPENCODE_CONFIG_PATH.read_bytes())

    plugins = data.get("plugin")
    if not isinstance(plugins, list):
        plugins = []
        data["plugin"] = plugins
    our_entry = _opencode_plugin_entry()
    if not any(_is_our_opencode_plugin(e) for e in plugins):
        plugins.append(our_entry)

    _write_json_atomic(OPENCODE_CONFIG_PATH, data)

    # Copy the plugin file AFTER writing the config: a config pointing at a
    # missing plugin is worse than no config at all (OpenCode would log an
    # error on every start).
    OPENCODE_PLUGIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENCODE_PLUGIN_PATH.write_bytes(OPENCODE_PLUGIN_SOURCE.read_bytes())
    # The shim runs this notify command with the agent argument "opencode".
    _opencode_command_path().write_text(HOOK_COMMAND, encoding="utf-8")

    logger.info(
        "Installed OpenCode plugin: shim at %s, entry in %s",
        OPENCODE_PLUGIN_PATH, OPENCODE_CONFIG_PATH,
    )
    return True


def uninstall_opencode_hooks() -> bool:
    """Remove the OpenCode plugin shim and our entry from opencode.json,
    restoring the user's original opencode.json byte-for-byte from the backup
    install() wrote. Idempotent; returns True when no entry or file of ours
    remains (including when nothing was ever installed). Returns False only
    when opencode.json exists but is unparseable — in that case it is left
    untouched."""
    backup = OPENCODE_CONFIG_PATH.with_name(
        OPENCODE_CONFIG_PATH.name + OPENCODE_BACKUP_SUFFIX
    )

    # Always remove the plugin file (it's ours to copy).
    try:
        OPENCODE_PLUGIN_PATH.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove OpenCode plugin file %s", OPENCODE_PLUGIN_PATH)
    try:
        _opencode_command_path().unlink(missing_ok=True)
    except OSError:
        pass

    if not OPENCODE_CONFIG_PATH.exists():
        # No config to clean up; backup file (if any) is orphaned, drop it.
        backup.unlink(missing_ok=True)
        return True

    if backup.exists():
        # Restore the original byte-for-byte, then drop the backup.
        OPENCODE_CONFIG_PATH.write_bytes(backup.read_bytes())
        backup.unlink(missing_ok=True)
        logger.info("Restored %s from backup", OPENCODE_CONFIG_PATH)
        return True

    # No backup means install never ran, or the user has already restored
    # manually. Either way, do a surgical removal of our entry only — never
    # touch the user's own plugin entries.
    data = _load_opencode_config()
    if data is None:
        logger.warning(
            "Not uninstalling OpenCode plugin: %s is not a readable JSON object; "
            "left untouched",
            OPENCODE_CONFIG_PATH,
        )
        return False
    plugins = data.get("plugin")
    if not isinstance(plugins, list) or not any(
        _is_our_opencode_plugin(e) for e in plugins
    ):
        return True
    kept = [e for e in plugins if not _is_our_opencode_plugin(e)]
    if kept:
        data["plugin"] = kept
    else:
        del data["plugin"]
    _write_json_atomic(OPENCODE_CONFIG_PATH, data)
    logger.info("Removed OpenCode plugin entry from %s", OPENCODE_CONFIG_PATH)
    return True


def are_opencode_hooks_installed() -> bool:
    """True iff the plugin file is in place AND opencode.json carries our
    entry. Idempotent with install(): a successful install returns True,
    a successful uninstall returns False."""
    if not OPENCODE_PLUGIN_PATH.is_file():
        return False
    data = _load_opencode_config()
    if not data:
        return False
    plugins = data.get("plugin")
    if not isinstance(plugins, list):
        return False
    return any(_is_our_opencode_plugin(e) for e in plugins)


# --- Antigravity (agy CLI + Antigravity IDE) plugin ---------------------------
#
# Antigravity loads hooks from plugins (a project-level .agents/hooks.json was
# verified NOT to load). So we write a local plugin folder (plugin.json +
# hooks.json), mirror it under ~/.clawd-tank and register it with
# `agy plugin install <dir>`; uninstall is `agy plugin uninstall margarita-tank`
# plus deleting our mirror. Other plugins are never touched.
#
# The hook payload does not name its event, so every registered command passes
# it as the last argument: `<notify> antigravity <Event>`.
ANTIGRAVITY_PLUGIN_NAME = "margarita-tank"
ANTIGRAVITY_PLUGIN_DIR = CLAWD_DIR / "antigravity-plugin" / ANTIGRAVITY_PLUGIN_NAME
ANTIGRAVITY_WRAPPER_PATH = CLAWD_DIR / "clawd-tank-antigravity.cmd"
ANTIGRAVITY_HOOK_TIMEOUT_SECONDS = 10
# (hook event, whether it carries a tool matcher). PostInvocation is not
# registered: the daemon has nothing to do with it.
ANTIGRAVITY_EVENTS = (
    ("PreInvocation", False),
    ("PreToolUse", True),
    ("PostToolUse", True),
    ("Stop", False),
)
AGY_COMMAND_TIMEOUT_SECONDS = 60


def build_antigravity_hook_command(
    platform: str, frozen: bool, executable, script_path, wrapper_path, event: str,
) -> str:
    """The command Antigravity runs for one hook event.

    agy's hook runner wraps and quotes commands badly on Windows: a quoted
    absolute interpreter path ends up as `node "C:\\a\\"C:\\a\\hook.js""` and
    fails. So on Windows the command is NEVER quoted. It names the executable
    (and script) directly when none of their paths contain whitespace, else it
    goes through a tiny space-free .cmd wrapper under ~/.clawd-tank
    (`wrapper_path`, see `antigravity_wrapper_script`); if even that path has
    whitespace there is no safe spelling and ValueError is raised.

    No `; exit 0` suffix on Windows: the runner's shell is unknown and cmd.exe
    would pass "PreToolUse;" to the program. The notify script exits 0 by
    itself, and the .cmd wrapper ends with `exit /b 0`. POSIX shells get the
    suffix explicitly.
    """
    if platform == "win32":
        if frozen:
            parts = [ntpath.join(ntpath.dirname(str(executable)), NOTIFY_EXE_NAME)]
        else:
            interpreter = str(executable)
            if ntpath.basename(interpreter).lower() == "pythonw.exe":
                interpreter = ntpath.join(ntpath.dirname(interpreter), "python.exe")
            parts = [interpreter, str(script_path)]
        if not any(c.isspace() for p in parts for c in p):
            return " ".join(parts + ["antigravity", event])
        if any(c.isspace() for c in str(wrapper_path)):
            raise ValueError(
                f"cannot build an Antigravity hook command: {wrapper_path} has "
                "whitespace and agy cannot run quoted commands on Windows"
            )
        return f"{wrapper_path} {event}"
    return f"{shlex.quote(str(script_path))} antigravity {event}; exit 0"


def antigravity_wrapper_script(frozen: bool, executable, script_path) -> str:
    """Contents of the Windows .cmd wrapper used when the interpreter/script
    paths contain spaces. Quotes are fine INSIDE the .cmd file (cmd.exe parses
    it itself); only the plugin command string cannot carry them. It forwards
    just the event (%1) and ends with `exit /b 0` so the agent never sees a
    failing hook."""
    if frozen:
        program = f'"{ntpath.join(ntpath.dirname(str(executable)), NOTIFY_EXE_NAME)}"'
    else:
        interpreter = str(executable)
        if ntpath.basename(interpreter).lower() == "pythonw.exe":
            interpreter = ntpath.join(ntpath.dirname(interpreter), "python.exe")
        program = f'"{interpreter}" "{script_path}"'
    return "\r\n".join([
        "@echo off",
        "rem Generated by Clawdy. Do not edit.",
        f"{program} antigravity %1",
        "exit /b 0",
        "",
    ])


def build_antigravity_hooks_json(commands: dict) -> dict:
    """The plugin's hooks.json: one named hook set ("margarita-tank") with a
    command per event in `commands` (event name -> command string). Tool events
    take a matcher group ("*" = every tool); the others are plain command lists."""
    body: dict = {"enabled": True}
    for event, with_matcher in ANTIGRAVITY_EVENTS:
        entry = {
            "type": "command",
            "command": commands[event],
            "timeout": ANTIGRAVITY_HOOK_TIMEOUT_SECONDS,
        }
        body[event] = [{"matcher": "*", "hooks": [entry]}] if with_matcher else [entry]
    return {ANTIGRAVITY_PLUGIN_NAME: body}


def build_antigravity_plugin_json(version: str) -> dict:
    return {"name": ANTIGRAVITY_PLUGIN_NAME, "version": version}


def antigravity_plugin_version(raw: str) -> str:
    """A stable semver for plugin.json. The app version in a dev checkout
    ("branch+N@sha-dirty") changes on every commit, which would look like an
    outdated plugin forever, so only a real X.Y.Z is used; anything else is
    0.0.0."""
    match = re.search(r"(\d+\.\d+\.\d+)", raw or "")
    return match.group(1) if match else "0.0.0"


def _find_agy() -> str | None:
    """Path to the agy CLI, or None when it is not installed. A tray app often
    has a thinner PATH than a terminal, so the Windows install location is a
    fallback."""
    found = shutil.which("agy")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "agy" / "bin" / "agy.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _run_agy(argv: list) -> bool:
    """Run an agy command (argv[0] is agy itself). True on exit code 0; any
    failure to run (missing binary, timeout, permissions) is False, never an
    exception."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, shell=False,
            timeout=AGY_COMMAND_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not run %s: %s", " ".join(map(str, argv[:3])), exc)
        return False
    if result.returncode != 0:
        logger.warning(
            "%s exited with %s: %s", " ".join(map(str, argv[:3])),
            result.returncode, (result.stderr or result.stdout or "").strip()[:200],
        )
        return False
    return True


def _antigravity_plan(platform, frozen, executable, script_path, wrapper_path):
    """The per-event hook commands, plus the .cmd wrapper text when the commands
    go through it (None otherwise). Raises ValueError when no safe command can
    be built (see build_antigravity_hook_command)."""
    commands = {
        event: build_antigravity_hook_command(
            platform, frozen, executable, script_path, wrapper_path, event)
        for event, _ in ANTIGRAVITY_EVENTS
    }
    uses_wrapper = any(str(wrapper_path) in command for command in commands.values())
    wrapper = antigravity_wrapper_script(frozen, executable, script_path) if uses_wrapper else None
    return commands, wrapper


def _antigravity_expected_files() -> tuple[dict, dict, str | None]:
    commands, wrapper = _antigravity_plan(
        sys.platform, getattr(sys, "frozen", False), _HOOK_EXECUTABLE,
        NOTIFY_SCRIPT_PATH, ANTIGRAVITY_WRAPPER_PATH,
    )
    plugin = build_antigravity_plugin_json(antigravity_plugin_version(get_version()))
    return plugin, build_antigravity_hooks_json(commands), wrapper


def are_antigravity_hooks_installed() -> bool:
    """True iff our mirrored plugin folder is present and current (same
    plugin.json, hooks.json and, when used, wrapper as install would write)."""
    if not ANTIGRAVITY_PLUGIN_DIR.is_dir():
        return False  # cheap exit: no need to compute the expected files
    try:
        plugin, hooks_json, wrapper = _antigravity_expected_files()
        on_disk_plugin = json.loads(
            (ANTIGRAVITY_PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8-sig"))
        on_disk_hooks = json.loads(
            (ANTIGRAVITY_PLUGIN_DIR / "hooks.json").read_text(encoding="utf-8-sig"))
        if wrapper is not None and (
            not ANTIGRAVITY_WRAPPER_PATH.is_file()
            or ANTIGRAVITY_WRAPPER_PATH.read_bytes() != wrapper.encode("utf-8")
        ):
            return False
    except (OSError, ValueError):
        return False
    return on_disk_plugin == plugin and on_disk_hooks == hooks_json


def _remove_antigravity_mirror() -> None:
    shutil.rmtree(ANTIGRAVITY_PLUGIN_DIR, ignore_errors=True)
    try:
        ANTIGRAVITY_WRAPPER_PATH.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove %s", ANTIGRAVITY_WRAPPER_PATH)
    try:
        ANTIGRAVITY_PLUGIN_DIR.parent.rmdir()  # only when empty: others may live there
    except OSError:
        pass


def install_antigravity_hooks() -> bool:
    """Write our local agy plugin and register it with `agy plugin install`.

    Does nothing (False) when agy is not installed. Idempotent: an already
    current plugin is not rewritten or re-registered. Only our own folder is
    ever written, and agy is only asked about our own plugin. Never raises."""
    agy = _find_agy()
    if agy is None:
        logger.warning("Not installing Antigravity hooks: agy was not found")
        return False
    try:
        if are_antigravity_hooks_installed():
            return True
        plugin, hooks_json, wrapper = _antigravity_expected_files()
    except ValueError as exc:
        logger.warning("Not installing Antigravity hooks: %s", exc)
        return False
    try:
        if wrapper is not None:
            _write_bytes_atomic(ANTIGRAVITY_WRAPPER_PATH, wrapper.encode("utf-8"))
        _write_json_atomic(ANTIGRAVITY_PLUGIN_DIR / "plugin.json", plugin)
        _write_json_atomic(ANTIGRAVITY_PLUGIN_DIR / "hooks.json", hooks_json)
    except OSError:
        logger.warning("Could not write the Antigravity plugin to %s", ANTIGRAVITY_PLUGIN_DIR)
        _remove_antigravity_mirror()
        return False
    if not _run_agy([agy, "plugin", "install", str(ANTIGRAVITY_PLUGIN_DIR)]):
        _remove_antigravity_mirror()
        return False
    logger.info("Installed Antigravity plugin %s", ANTIGRAVITY_PLUGIN_NAME)
    return True


def uninstall_antigravity_hooks() -> bool:
    """`agy plugin uninstall margarita-tank` and delete our mirror. A no-op
    (True) when we never installed. Without agy there is nothing to
    unregister, so only the mirror goes. The mirror is always removed; the
    result is False only when agy itself refused. Never touches other plugins."""
    if not ANTIGRAVITY_PLUGIN_DIR.exists():
        return True
    agy = _find_agy()
    ok = True
    if agy is not None:
        ok = _run_agy([agy, "plugin", "uninstall", ANTIGRAVITY_PLUGIN_NAME])
    _remove_antigravity_mirror()
    if ok:
        logger.info("Uninstalled Antigravity plugin %s", ANTIGRAVITY_PLUGIN_NAME)
    return ok


# --- Pi (gentle-shell) extension (S4) ----------------------------------------
# Pi loads <agent-dir>/extensions/*.js. We own exactly two files there: the
# extension and its notify command. Nothing else in extensions/ is touched.

PI_EXTENSION_NAME = "clawd-tank.js"


def resolve_pi_extension_source(frozen, executable, resourcepath, module_file) -> Path:
    """Where the bundled Pi extension ships from: host/pi-extension/ in a source
    checkout, next to the exe in a PyInstaller build (same rule as the OpenCode shim)."""
    if frozen:
        base = Path(resourcepath) if resourcepath else Path(executable).parent
    else:
        base = Path(module_file).parents[1]
    return base / "pi-extension" / PI_EXTENSION_NAME


PI_EXTENSION_SOURCE = resolve_pi_extension_source(
    bool(getattr(sys, "frozen", False)), sys.executable,
    os.environ.get("RESOURCEPATH"), Path(__file__).resolve(),
)
PI_COMMAND_NAME = "clawd-tank.command"


def _pi_extensions_dir(agent_dir=None) -> Path:
    if agent_dir is None:
        env = os.environ.get("PI_CODING_AGENT_DIR")
        agent_dir = Path(env) if env else Path.home() / ".gentle-shell" / "agent"
    return Path(agent_dir) / "extensions"


def _pi_extension_dirs(agent_dir=None) -> list:
    """Every extensions/ folder that gets our files. An explicit agent_dir means only that one.
    Otherwise Gentle Shell's agent dir (or PI_CODING_AGENT_DIR) always, plus a plain Pi's
    ~/.pi/agent when it exists: `pi` run on its own reads that one, not Gentle Shell's."""
    primary = _pi_extensions_dir(agent_dir)
    if agent_dir is not None:
        return [primary]
    plain = Path.home() / ".pi" / "agent"
    dirs = [primary]
    if plain.is_dir() and plain / "extensions" != primary:
        dirs.append(plain / "extensions")
    return dirs


def install_pi_hooks(agent_dir=None) -> bool:
    """Copy the Pi extension and write its notify command into every target. False if
    the bundled source is missing; nothing is written in that case."""
    if not PI_EXTENSION_SOURCE.is_file():
        logger.warning("Not installing Pi extension: bundled source %s not found", PI_EXTENSION_SOURCE)
        return False
    for ext_dir in _pi_extension_dirs(agent_dir):
        ext_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PI_EXTENSION_SOURCE, ext_dir / PI_EXTENSION_NAME)
        (ext_dir / PI_COMMAND_NAME).write_text(HOOK_COMMAND, encoding="utf-8")
        logger.info("Installed Pi extension in %s", ext_dir)
    return True


def uninstall_pi_hooks(agent_dir=None) -> bool:
    """Remove only the two files we own, from every target. Idempotent; always True."""
    for ext_dir in _pi_extension_dirs(agent_dir):
        for name in (PI_EXTENSION_NAME, PI_COMMAND_NAME):
            (ext_dir / name).unlink(missing_ok=True)
    return True


def are_pi_hooks_installed(agent_dir=None) -> bool:
    """True only when every target holds the current extension and its command."""
    if not PI_EXTENSION_SOURCE.is_file():
        return False
    for ext_dir in _pi_extension_dirs(agent_dir):
        ext = ext_dir / PI_EXTENSION_NAME
        if not ((ext_dir / PI_COMMAND_NAME).is_file() and ext.is_file()
                and ext.read_bytes() == PI_EXTENSION_SOURCE.read_bytes()):
            return False
    return True
