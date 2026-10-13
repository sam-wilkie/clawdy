"""End-to-end: Antigravity hook payloads, fed through the daemon, drive the same
display animations as other agents and show up as their own product slot.

Exercises translation -> daemon._handle_message -> per-session state ->
_compute_display_state, without any transport or hardware.
"""

import asyncio

from clawd_tank_daemon.antigravity_protocol import (
    ANTIGRAVITY_SESSION_PREFIX,
    antigravity_hook_payload_to_daemon_message,
)
from clawd_tank_daemon.daemon import ClawdDaemon

CLI_TRANSCRIPT = "C:/Users/Matt/.gemini/antigravity-cli/brain/c1/x.jsonl"
IDE_TRANSCRIPT = "C:/Users/Matt/.gemini/antigravity-ide/brain/c1/x.jsonl"


def make_daemon():
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    return d


def feed(d, event, conversation="c1", **fields):
    payload = {
        "hookEventName": event,
        "conversationId": conversation,
        "workspacePaths": ["C:/work/proj"],
        "transcriptPath": CLI_TRANSCRIPT,
    }
    payload.update(fields)
    msg = antigravity_hook_payload_to_daemon_message(payload)
    assert msg is not None, f"{event} should translate"
    asyncio.run(d._handle_message(msg))
    return msg


def tool(name):
    return {"toolCall": {"name": name, "args": {}}}


def test_stop_fallback_never_overwrites_a_real_project():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    assert session(d)["project"] == "proj"
    feed(d, "Stop", fullyIdle=True, workspacePaths=[])  # fallback title
    assert session(d)["project"] == "proj"
    feed(d, "Stop", error="boom", fullyIdle=True, workspacePaths=[])
    assert session(d)["project"] == "proj"


def test_stop_with_a_workspace_keeps_the_folder_as_session_project():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    feed(d, "Stop", fullyIdle=True)
    assert session(d)["project"] == "proj"


def test_antigravity_session_is_its_own_product():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    state = d._compute_display_state()
    assert state["agents"] == ["antigravity"]
    assert state["products"] == [
        {"agent": "antigravity", "count": 1, "anim": "building"}
    ]
    assert ANTIGRAVITY_SESSION_PREFIX + "c1" in d._session_states
    assert "c1" not in d._session_states


def anims(d):
    return d._compute_display_state()["anims"]


def session(d, conversation="c1"):
    return d._session_states[ANTIGRAVITY_SESSION_PREFIX + conversation]


def test_first_event_starts_the_session_implicitly_as_thinking():
    d = make_daemon()
    feed(d, "PreInvocation", invocationNum=1, initialNumSteps=0)
    assert session(d)["state"] == "thinking"
    assert anims(d) == ["thinking"]
    assert session(d).get("project") == "proj"


def test_tool_lifecycle_thinking_working_done():
    d = make_daemon()
    feed(d, "PreInvocation")
    feed(d, "PreToolUse", **tool("grep_search"))
    assert anims(d) == ["debugger"]
    feed(d, "PostToolUse", **tool("grep_search"))
    assert anims(d) == ["debugger"]  # tool_done keeps the working state


def test_ask_question_surfaces_as_waiting_alert_then_resumes():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("ask_question"))
    assert session(d)["state"] == "waiting"
    assert anims(d) == ["alert"]
    feed(d, "PostToolUse", **tool("ask_question"))
    assert session(d)["state"] == "thinking"


def test_ask_permission_surfaces_as_waiting_alert():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("ask_permission"))
    assert anims(d) == ["alert"]


def test_stop_fully_idle_ends_the_turn_calmly_without_a_card():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    feed(d, "Stop", terminationReason="NO_TOOL_CALL", error="", fullyIdle=True)
    assert session(d)["state"] == "waiting"
    assert session(d)["awaiting_prompt"] is True
    assert anims(d) == ["waiting_reply"]
    assert d._active_notifications == {}


def test_stop_with_background_work_leaves_the_session_working():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    msg = antigravity_hook_payload_to_daemon_message({
        "hookEventName": "Stop", "conversationId": "c1", "fullyIdle": False,
        "error": "", "terminationReason": "NO_TOOL_CALL",
    })
    assert msg is None
    assert session(d)["state"] == "working"


def test_stop_error_shows_the_dizzy_error_state_and_a_card():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    feed(d, "Stop", terminationReason="error", error="boom", fullyIdle=True)
    assert session(d)["state"] == "error"
    assert anims(d) == ["dizzy"]
    assert d._active_notifications[ANTIGRAVITY_SESSION_PREFIX + "c1"]["message"] == "boom"


def test_failed_tool_makes_the_crab_confused_and_web_failure_hat_mishap():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    feed(d, "PostToolUse", error="nope", **tool("run_command"))
    assert anims(d) == ["confused"]
    feed(d, "PreToolUse", **tool("search_web"))
    feed(d, "PostToolUse", error="nope", **tool("search_web"))
    assert anims(d) == ["hat_mishap"]


def test_a_late_post_tool_use_never_resurrects_a_session():
    d = make_daemon()
    feed(d, "PostToolUse", **tool("view_file"))
    assert d._session_states == {}


def test_two_conversations_are_two_crabs_and_do_not_touch_claude_ids():
    d = make_daemon()
    feed(d, "PreToolUse", conversation="c1", **tool("run_command"))
    feed(d, "PreToolUse", conversation="c2", **tool("view_file"))
    asyncio.run(d._handle_message({
        "event": "tool_use", "session_id": "c1", "tool_name": "Bash",
        "project": "p", "pid": None,
    }))
    assert len(d._session_states) == 3
    assert d._compute_display_state()["agents"].count("antigravity") == 2
    assert d._compute_display_state()["agents"].count("claude") == 1


def test_antigravity_session_without_pid_is_not_pid_watched():
    d = make_daemon()
    feed(d, "PreToolUse", **tool("run_command"))
    # No PID: eviction falls to the no-PID staleness timeout, like OpenCode.
    assert session(d).get("pid") is None


# --- The real notify scripts (embedded + standalone) ---------------------------
#
# Antigravity runs the installed hook command as `<notify> antigravity <Event>`
# and pipes the camelCase payload on stdin. A PreToolUse hook is a gate: the
# script must always answer {"decision":"allow"} and exit 0, even with the
# daemon down or garbage on stdin, so it can never block the agent.

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

import pytest

from clawd_tank_menubar.hooks import NOTIFY_SCRIPT
from tests.test_notify_script import STANDALONE_PATH, WINDOWS, _listen, _make_sock_path

NOTIFY_VARIANTS = ["embedded", "standalone"]


def run_notify(variant, event, payload, *, daemon=True, raw_stdin=None, tmp_path=None):
    """Run a notify script as the Antigravity hook would. Returns (process,
    message the fake daemon received or {})."""
    received = {}
    home = None
    if variant == "standalone":
        home = tempfile.mkdtemp(prefix="ct_", dir=None if WINDOWS else "/tmp")
        clawd = os.path.join(home, ".clawd-tank")
        os.mkdir(clawd)
        with open(os.path.join(clawd, "daemon.pid"), "w") as f:
            f.write(str(os.getpid()))  # a live process: do not try to start one
        sock_path = os.path.join(clawd, "endpoint.json" if WINDOWS else "sock")
    else:
        sock_path = _make_sock_path()

    srv = thread = None
    if daemon:
        srv, token = _listen(sock_path)

        def serve():
            try:
                conn, _ = srv.accept()
                conn.settimeout(3.0)
                data = b""
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    data += chunk
                conn.close()
                lines = data.decode("utf-8").splitlines()
                if WINDOWS and lines:
                    lines.pop(0)  # token
                if lines and lines[0].strip():
                    received.update(json.loads(lines[0]))
            except OSError:
                pass
            finally:
                srv.close()

        thread = threading.Thread(target=serve)
        thread.start()

    env = os.environ.copy()
    script_path = None
    try:
        if variant == "standalone":
            argv = [sys.executable, str(STANDALONE_PATH)]
            env["HOME"] = home
            env["USERPROFILE"] = home
        else:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                             encoding="utf-8") as f:
                f.write(NOTIFY_SCRIPT)
                script_path = f.name
            argv = [sys.executable, script_path]
            env["CLAWD_TANK_SOCKET"] = sock_path
        argv += ["antigravity"] + ([event] if event else [])
        stdin = raw_stdin if raw_stdin is not None else json.dumps(payload).encode("utf-8")
        proc = subprocess.run(argv, input=stdin, env=env, timeout=15.0,
                              capture_output=True)
    finally:
        if script_path:
            os.unlink(script_path)
        if thread:
            thread.join(timeout=8.0)
        if home:
            shutil.rmtree(home, ignore_errors=True)
        elif os.path.exists(sock_path):
            try:
                os.unlink(sock_path)
            except OSError:
                pass
    return proc, received


RAW_PRE_TOOL = {
    "conversationId": "c9",
    "workspacePaths": ["C:/work/proj"],
    "transcriptPath": CLI_TRANSCRIPT,
    "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}},
    "stepIdx": 2,
}


@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_forwards_pre_tool_use_and_answers_allow(variant):
    proc, msg = run_notify(variant, "PreToolUse", RAW_PRE_TOOL)
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8")) == {"decision": "allow"}
    assert msg["event"] == "tool_use"
    assert msg["session_id"] == "antigravity:c9"
    assert msg["tool_name"] == "Bash"
    assert msg["project"] == "proj"


@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_still_allows_and_exits_zero_when_the_daemon_is_down(variant):
    proc, msg = run_notify(variant, "PreToolUse", RAW_PRE_TOOL, daemon=False)
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8")) == {"decision": "allow"}
    assert msg == {}


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1, 2]", b"\xff\xfe"],
                         ids=["empty", "junk", "list", "bad-bytes"])
@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_allows_the_gate_even_with_unusable_stdin(variant, raw):
    proc, msg = run_notify(variant, "PreToolUse", None, raw_stdin=raw, daemon=False)
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8")) == {"decision": "allow"}


@pytest.mark.parametrize("event,extra", [
    ("PostToolUse", {"toolCall": {"name": "view_file", "args": {}}}),
    ("PreInvocation", {"invocationNum": 1}),
    ("Stop", {"fullyIdle": True, "error": "", "terminationReason": "NO_TOOL_CALL"}),
])
@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_prints_nothing_for_non_gating_events(variant, event, extra):
    payload = {**RAW_PRE_TOOL, **extra}
    proc, msg = run_notify(variant, event, payload)
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert msg["session_id"] == "antigravity:c9"


@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_maps_each_event_name_it_is_given(variant):
    _, done = run_notify(variant, "PostToolUse",
                         {**RAW_PRE_TOOL, "toolCall": {"name": "view_file", "args": {}}})
    assert (done["event"], done["tool_name"]) == ("tool_done", "Read")
    _, think = run_notify(variant, "PreInvocation", RAW_PRE_TOOL)
    assert (think["event"], think["hook"]) == ("dismiss", "UserPromptSubmit")
    _, stop = run_notify(variant, "Stop", {**RAW_PRE_TOOL, "fullyIdle": True})
    assert (stop["event"], stop["hook"], stop["project"]) == ("add", "Stop", "proj")


@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_does_not_send_a_stop_that_leaves_background_work_running(variant):
    proc, msg = run_notify(variant, "Stop", {**RAW_PRE_TOOL, "fullyIdle": False,
                                             "error": ""})
    assert proc.returncode == 0
    assert msg == {}


@pytest.mark.parametrize("variant", NOTIFY_VARIANTS)
def test_notify_without_an_event_name_sends_nothing_and_never_fails(variant):
    proc, msg = run_notify(variant, "", RAW_PRE_TOOL)
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert msg == {}


def test_embedded_translator_matches_the_daemon_side_translator():
    """The notify script cannot import the daemon package, so it carries a copy
    of the translator. Both must agree on every event."""
    namespace = {"__name__": "embedded_copy"}
    exec(compile(NOTIFY_SCRIPT, "<notify>", "exec"), namespace)
    embedded = namespace["antigravity_hook_to_message"]
    payloads = []
    for event in ("PreInvocation", "PostInvocation", "PreToolUse", "PostToolUse",
                  "Stop", "Bogus"):
        for tool_name in ("run_command", "ask_question", "mcp__a__b", "zzz"):
            for stop in ({"fullyIdle": True}, {"fullyIdle": False},
                         {"error": "x", "fullyIdle": True},
                         {"terminationReason": "error", "error": "out of credits"}):
                for ws in (["C:/w/p"], [], None):
                    payloads.append({
                        "hookEventName": event, "conversationId": "k",
                        "workspacePaths": ws, "transcriptPath": IDE_TRANSCRIPT,
                        "toolCall": {"name": tool_name, "args": {}},
                        "error": stop.get("error", ""), **stop,
                    })
    payloads.append({"hookEventName": "PreInvocation", "conversationId": ""})
    for payload in payloads:
        assert embedded(payload) == antigravity_hook_payload_to_daemon_message(payload), payload
