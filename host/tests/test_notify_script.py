"""End-to-end test of the embedded NOTIFY_SCRIPT: write it to a tempfile,
invoke as a subprocess with a hook payload on stdin, assert it writes the
expected JSON to the daemon's ingress — a Unix socket on POSIX, an
authenticated loopback TCP connection on Windows.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from clawd_tank_menubar.hooks import NOTIFY_SCRIPT
from clawd_tank_daemon.protocol import hook_payload_to_daemon_message

WINDOWS = sys.platform == "win32"


def _make_sock_path() -> str:
    """Return the path the script will be pointed at through CLAWD_TANK_SOCKET.

    POSIX: the Unix socket itself, which must be short — pytest's tmp_path on
    macOS expands to a very long path under /private/var/folders/... that
    exceeds AF_UNIX's 104-byte limit, so it goes in /tmp instead.
    Windows: the endpoint file the daemon publishes its port and token in. No
    length limit applies, so the platform temp directory is fine.
    """
    fd, path = tempfile.mkstemp(
        prefix="ct_",
        suffix=".json" if WINDOWS else ".sock",
        dir=None if WINDOWS else "/tmp",
    )
    os.close(fd)
    os.unlink(path)  # bind() requires the file to not exist
    return path


def _listen(sock_path: str) -> tuple[socket.socket, str]:
    """Bind the ingress the script will connect to, returning it and the token
    it must present. On Windows the port and token are published exactly the way
    SocketServer publishes them; on POSIX there is no token."""
    if WINDOWS:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        token = secrets.token_urlsafe(32)
        Path(sock_path).write_text(
            json.dumps({"port": srv.getsockname()[1], "token": token}),
            encoding="utf-8",
        )
    else:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path)
        token = ""
    srv.listen(1)
    srv.settimeout(5.0)
    return srv, token


def _run_script_with_payload(payload: dict, sock_path: str,
                             auth_out: list | None = None) -> dict:
    """Run NOTIFY_SCRIPT in a subprocess with payload on stdin; return the JSON
    message it sent to the ingress. Returns {} if nothing arrived.

    The token is enforced, not just observed: a script that failed to
    authenticate delivers nothing, so every test here covers the handshake.
    Pass auth_out to also capture the line the script offered as its token.
    """
    received = {}
    srv, token = _listen(sock_path)

    def server():
        try:
            conn, _ = srv.accept()
            data = b""
            conn.settimeout(2.0)
            while True:
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                data += chunk
            conn.close()
            lines = data.decode("utf-8").splitlines()
            if WINDOWS:
                offered = lines.pop(0) if lines else ""
                if auth_out is not None:
                    auth_out.append(offered)
                if offered != token:
                    return
            if lines and lines[0].strip():
                received.update(json.loads(lines[0]))
        except socket.timeout:
            pass
        finally:
            srv.close()
            try:
                os.unlink(sock_path)
            except (FileNotFoundError, PermissionError):
                pass

    t = threading.Thread(target=server)
    t.start()

    # encoding="utf-8" matches install_notify_script(); without it Windows
    # writes the script in the locale codepage and the interpreter refuses
    # to parse its own source.
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(NOTIFY_SCRIPT)
        script_path = f.name
    os.chmod(script_path, 0o755)

    try:
        # Override the socket path the script uses via env (we'll modify the
        # script to honor CLAWD_TANK_SOCKET if set — see Step 3).
        env = os.environ.copy()
        env["CLAWD_TANK_SOCKET"] = sock_path
        subprocess.run(
            [sys.executable, script_path],
            input=json.dumps(payload).encode("utf-8"),
            env=env,
            timeout=5.0,
            capture_output=True,
        )
    finally:
        os.unlink(script_path)

    t.join(timeout=3.0)
    return received


def _assert_pid(msg: dict) -> None:
    """The script stamps the resolved Claude Code PID on POSIX. On Windows it
    stamps a claude.exe ancestor's PID, or none at all when there is no such
    ancestor — see NOTIFY_SCRIPT._find_claude_pid — so the daemon never watches
    a PID that is not Claude Code's. Which one depends on whether this suite
    itself runs under Claude Code."""
    if WINDOWS:
        pid = msg.get("pid")
        if pid is not None:
            from clawd_tank_daemon.pid_resolver import _windows_process_table
            _, name = _windows_process_table()[pid]
            assert name.lower() == "claude.exe"
    else:
        assert isinstance(msg.get("pid"), int)
        assert msg["pid"] > 0


def test_notify_script_stamps_pid_on_session_start(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SessionStart",
        "session_id": "test-session-123",
        "cwd": str(tmp_path),
        "source": "startup",
    }, sock_path)
    assert msg.get("event") == "session_start"
    assert msg.get("session_id") == "test-session-123"
    _assert_pid(msg)
    assert msg.get("source") == "startup"


def test_notify_script_stamps_pid_on_stop(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "Stop",
        "session_id": "s2",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "add"
    assert msg.get("hook") == "Stop"
    _assert_pid(msg)


def test_notify_script_session_end_includes_reason(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SessionEnd",
        "session_id": "s3",
        "reason": "logout",
    }, sock_path)
    assert msg.get("event") == "dismiss"
    assert msg.get("hook") == "SessionEnd"
    assert msg.get("reason") == "logout"
    _assert_pid(msg)


def test_notify_script_irrelevant_hook_sends_nothing(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SomeUnhandledEvent",  # not handled
        "session_id": "s4",
    }, sock_path)
    assert msg == {}


def test_notify_script_post_tool_use_produces_tool_done(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PostToolUse",
        "session_id": "s5",
        "tool_name": "AskUserQuestion",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "tool_done"
    assert msg.get("session_id") == "s5"
    assert msg.get("tool_name") == "AskUserQuestion"
    _assert_pid(msg)


def test_notify_script_permission_request_produces_permission(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PermissionRequest",
        "session_id": "s6",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "permission"
    assert msg.get("session_id") == "s6"
    assert msg.get("tool_name") == "Bash"
    _assert_pid(msg)


def test_notify_script_post_tool_use_failure_produces_tool_failed(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PostToolUseFailure",
        "session_id": "s7",
        "tool_name": "Read",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "tool_failed"
    assert msg.get("session_id") == "s7"
    assert msg.get("tool_name") == "Read"
    _assert_pid(msg)


# --- Cross-validate the embedded script against the daemon-side converter ---
# The NOTIFY_SCRIPT is stdlib-only and cannot import protocol.py, so the two
# hook->message mappings are duplicated and must stay in sync. This guards drift.

_CROSS_CHECK_HOOKS = [
    {"hook_event_name": "SessionStart", "session_id": "s", "cwd": "/x/proj", "source": "startup"},
    {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/x/proj", "tool_name": "Bash"},
    {"hook_event_name": "PostToolUse", "session_id": "s", "cwd": "/x/proj", "tool_name": "AskUserQuestion"},
    {"hook_event_name": "PermissionRequest", "session_id": "s", "cwd": "/x/proj", "tool_name": "Bash"},
    {"hook_event_name": "PostToolUseFailure", "session_id": "s", "cwd": "/x/proj", "tool_name": "Read"},
    {"hook_event_name": "PreCompact", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "Stop", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "StopFailure", "session_id": "s", "cwd": "/x/proj", "error": "boom"},
    {"hook_event_name": "StopFailure", "session_id": "s", "cwd": "/x/proj", "error": "billing_error"},
    {"hook_event_name": "StopFailure", "session_id": "s", "cwd": "/x/proj", "error": "rate_limit"},
    {"hook_event_name": "Notification", "notification_type": "idle_prompt",
     "session_id": "s", "cwd": "/x/proj", "message": "m"},
    {"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "SessionEnd", "session_id": "s", "cwd": "/x/proj", "reason": "logout"},
    {"hook_event_name": "SubagentStart", "session_id": "s", "cwd": "/x/proj", "agent_id": "a"},
    {"hook_event_name": "SubagentStop", "session_id": "s", "cwd": "/x/proj", "agent_id": "a"},
]


@pytest.mark.parametrize("hook", _CROSS_CHECK_HOOKS,
                         ids=[h["hook_event_name"] for h in _CROSS_CHECK_HOOKS])
def test_notify_script_matches_protocol_converter(hook):
    """The embedded NOTIFY_SCRIPT must emit the same daemon message as the daemon-side
    protocol.hook_payload_to_daemon_message (modulo pid, which the script computes from
    the process tree while protocol reads it from the payload)."""
    sock_path = _make_sock_path()
    script_msg = _run_script_with_payload(hook, sock_path)
    proto_msg = hook_payload_to_daemon_message(hook) or {}
    script_msg.pop("pid", None)
    proto_msg = {k: v for k, v in proto_msg.items() if k != "pid"}
    assert script_msg == proto_msg


# --- Windows ingress handshake -----------------------------------------------


@pytest.mark.skipif(not WINDOWS, reason="only the Windows ingress is authenticated")
def test_notify_script_presents_the_published_token_first():
    """The script must read the token the daemon published and send it ahead of
    the message; without it the server closes the connection unread."""
    sock_path = _make_sock_path()
    offered: list[str] = []
    msg = _run_script_with_payload(
        {"hook_event_name": "Stop", "session_id": "s8", "cwd": "/x/proj"},
        sock_path, auth_out=offered,
    )
    assert msg.get("event") == "add"  # delivered, so the token matched
    assert offered and offered[0]
    assert offered[0] != json.dumps(msg)  # it is the token line, not the payload


@pytest.mark.skipif(not WINDOWS, reason="only the Windows ingress is authenticated")
def test_notify_script_stays_quiet_when_the_endpoint_file_is_unusable():
    """A stale, truncated or missing endpoint file must make the hook a no-op, not
    a crash: notifications are best-effort and a non-zero exit is noise in
    Claude Code."""
    for content in (None, "", "{}", "not json"):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "endpoint.json"
            if content is not None:
                path.write_text(content, encoding="utf-8")

            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                             encoding="utf-8") as f:
                f.write(NOTIFY_SCRIPT)
                script_path = f.name
            try:
                env = os.environ.copy()
                env["CLAWD_TANK_SOCKET"] = str(path)
                result = subprocess.run(
                    [sys.executable, script_path],
                    input=json.dumps({"hook_event_name": "Stop", "session_id": "s",
                                      "cwd": "/x/proj"}).encode("utf-8"),
                    env=env, timeout=5.0, capture_output=True,
                )
            finally:
                os.unlink(script_path)
            assert result.returncode == 0, f"endpoint {content!r}: {result.stderr}"


def test_notify_script_exits_zero_on_non_json_stdin():
    """Stdin that is not JSON must make the hook a silent no-op (exit 0), not a
    failure: a non-zero exit makes Codex report 'Hook failed, exited with code 1'
    for a fire-and-forget notifier that has nothing to forward anyway."""
    for raw in ("not json at all", "<<<garbage>>>", "{unterminated"):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as f:
            f.write(NOTIFY_SCRIPT)
            script_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, script_path, "codex"],
                input=raw.encode("utf-8"),
                timeout=5.0, capture_output=True,
            )
        finally:
            os.unlink(script_path)
        assert result.returncode == 0, f"input {raw!r}: rc={result.returncode} {result.stderr}"


# --- PermissionRequest: wait for the desk window's decision -------------------
#
# Both hook copies (the embedded NOTIFY_SCRIPT, which is what gets installed and
# frozen into margarita-notify.exe, and the standalone host/clawd-tank-notify)
# must send the message with wait + tool_summary, then keep the connection open
# and print the decision for Claude Code. Only an explicit allow/deny may reach
# stdout; every other outcome prints nothing so Claude Code asks in the terminal.

STANDALONE_PATH = Path(__file__).resolve().parent.parent / "clawd-tank-notify"

ALLOW_JSON = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                     "decision": {"behavior": "allow"}}}
DENY_JSON = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                    "decision": {"behavior": "deny",
                                                 "message": "Denied from Clawdy desk window"}}}

_PERMISSION_HOOK = {
    "hook_event_name": "PermissionRequest",
    "session_id": "sw",
    "tool_name": "Bash",
    "cwd": "/x/proj",
    "tool_input": {"command": "rm -rf build\necho done"},
}


def _run_permission_script(variant, reply_mode, wait_seconds="3", tmp_dir=None):
    """Run a hook copy against a fake daemon that answers per `reply_mode`.

    Returns (completed process, message the server received or {}, elapsed s).
    `variant` is "embedded" or "standalone". reply_mode is the raw bytes to send
    back, "noreply" (hold the connection open silently), or "close" (hang up).
    """
    import time as _time

    received = {}
    if variant == "standalone":
        home = tempfile.mkdtemp(prefix="ct_", dir=None if WINDOWS else "/tmp")
        clawd = Path(home) / ".clawd-tank"
        clawd.mkdir()
        (clawd / "daemon.pid").write_text(str(os.getpid()))  # a live process
        sock_path = str(clawd / ("endpoint.json" if WINDOWS else "sock"))
    else:
        home = None
        sock_path = _make_sock_path()
    srv, token = _listen(sock_path)

    def server():
        try:
            conn, _ = srv.accept()
            conn.settimeout(5.0)
            buf = b""
            wanted = 2 if WINDOWS else 1
            while buf.count(b"\n") < wanted:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            lines = buf.decode("utf-8").splitlines()
            if WINDOWS:
                if not lines or lines.pop(0) != token:
                    conn.close()
                    return
            if lines:
                received.update(json.loads(lines[0]))
            if reply_mode == "close":
                conn.close()
                return
            if reply_mode == "noreply":
                try:
                    conn.settimeout(8.0)
                    conn.recv(1)  # returns when the script hangs up
                except OSError:
                    pass
                conn.close()
                return
            conn.sendall(reply_mode)
            try:
                conn.settimeout(8.0)
                conn.recv(1)
            except OSError:
                pass
            conn.close()
        except (socket.timeout, OSError):
            pass
        finally:
            srv.close()
            try:
                os.unlink(sock_path)
            except (FileNotFoundError, PermissionError):
                pass

    t = threading.Thread(target=server)
    t.start()

    env = os.environ.copy()
    env["CLAWD_PERMISSION_WAIT"] = str(wait_seconds)
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
        started = _time.monotonic()
        proc = subprocess.run(
            argv, input=json.dumps(_PERMISSION_HOOK).encode("utf-8"),
            env=env, timeout=15.0, capture_output=True,
        )
        elapsed = _time.monotonic() - started
    finally:
        if script_path:
            os.unlink(script_path)
    t.join(timeout=12.0)
    if home:
        import shutil
        shutil.rmtree(home, ignore_errors=True)
    return proc, received, elapsed


VARIANTS = ["embedded", "standalone"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_sends_wait_and_summary(variant):
    proc, msg, _ = _run_permission_script(variant, b'{"decision":"none"}\n')
    assert msg.get("event") == "permission"
    assert msg.get("wait") is True
    assert msg.get("tool_name") == "Bash"
    assert msg.get("tool_summary") == "rm -rf build echo done"
    assert "tool_input" not in msg


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_prints_allow_json(variant):
    proc, _, _ = _run_permission_script(variant, b'{"decision":"allow"}\n')
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8")
    assert json.loads(out) == ALLOW_JSON
    assert len(out.strip().splitlines()) == 1


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_prints_deny_json_with_message(variant):
    proc, _, _ = _run_permission_script(variant, b'{"decision":"deny"}\n')
    assert proc.returncode == 0
    assert json.loads(proc.stdout.decode("utf-8")) == DENY_JSON


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("reply_mode", [
    b'{"decision":"none"}\n',
    b'garbage\n',
    b'\n',
    b'[]\n',
    b'{"decision":"maybe"}\n',
    b'{"decision":"ALLOW"}\n',
    b'{"decision":true}\n',
    b'{"decision":"allow"}',          # no newline: not a complete reply
    b'{"allow":true}\n',
    b'x' * 20000,                     # oversized junk
    "close",
], ids=["none", "garbage", "blank", "list", "maybe", "upper", "bool",
        "unterminated", "wrong-key", "oversized", "closed-early"])
def test_permission_hook_prints_nothing_for_anything_but_allow_or_deny(variant, reply_mode):
    proc, msg, _ = _run_permission_script(variant, reply_mode)
    assert msg.get("wait") is True
    assert proc.returncode == 0
    assert proc.stdout == b""


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_gives_up_silently_when_the_daemon_never_answers(variant):
    proc, _, elapsed = _run_permission_script(variant, "noreply", wait_seconds="0.6")
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert 0.5 <= elapsed < 6


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_default_wait_is_sixty_seconds(variant):
    """The default wait is 60 s; CLAWD_PERMISSION_WAIT (a test knob) may only shorten it, never
    stretch it past the limit the installed hook timeout is sized for."""
    import re
    if variant == "embedded":
        assert re.search(r"^PERMISSION_WAIT_SECONDS = 15$", NOTIFY_SCRIPT, re.M)
    else:
        from tests.test_notify_standalone import _load_notify_script
        assert _load_notify_script().PERMISSION_WAIT_SECONDS == 15


@pytest.mark.parametrize("variant", VARIANTS)
def test_permission_hook_with_no_daemon_prints_nothing(variant, tmp_path):
    """Connect failure: silent, exit 0, never an allow."""
    env = os.environ.copy()
    env["CLAWD_PERMISSION_WAIT"] = "1"
    if variant == "standalone":
        home = tempfile.mkdtemp(prefix="ct_", dir=None if WINDOWS else "/tmp")
        (Path(home) / ".clawd-tank").mkdir()
        (Path(home) / ".clawd-tank" / "daemon.pid").write_text(str(os.getpid()))
        env["HOME"] = home
        env["USERPROFILE"] = home
        argv = [sys.executable, str(STANDALONE_PATH)]
    else:
        script = tmp_path / "hook.py"
        script.write_text(NOTIFY_SCRIPT, encoding="utf-8")
        env["CLAWD_TANK_SOCKET"] = str(tmp_path / "missing.sock")
        argv = [sys.executable, str(script)]
    proc = subprocess.run(argv, input=json.dumps(_PERMISSION_HOOK).encode("utf-8"),
                          env=env, timeout=15.0, capture_output=True)
    assert proc.returncode == 0
    assert proc.stdout == b""


def test_embedded_summary_matches_protocol_summary():
    """The embedded script cannot import protocol.py; its summary builder must
    agree with permission_tool_summary on awkward input."""
    from clawd_tank_daemon.protocol import permission_tool_summary
    namespace = {"__name__": "embedded_copy"}
    exec(compile(NOTIFY_SCRIPT, "<notify>", "exec"), namespace)
    cases = [
        ("Bash", {"command": "a\tb\x1b[0m\r\nc" + "z" * 300}),
        ("Edit", {"file_path": "/p/é.py", "new_string": "x"}),
        ("Write", {"file_path": "/p/w.py"}),
        ("Read", {"file_path": 5}),
        ("WebFetch", {"url": "http://x"}),
        ("Bash", None),
        ("Bash", {"command": "   "}),
        ("", {}),
    ]
    for tool, tool_input in cases:
        assert namespace["_tool_summary"](tool, tool_input) == permission_tool_summary(tool, tool_input)


_PERMISSION_CROSS_CHECK = dict(_PERMISSION_HOOK)


def test_embedded_permission_message_matches_protocol_converter():
    """Cross-check for the new wait/tool_summary fields (the generic cross-check
    above sends a payload without tool_input, which would not exercise them)."""
    proc, script_msg, _ = _run_permission_script("embedded", b'{"decision":"none"}\n')
    proto_msg = hook_payload_to_daemon_message(_PERMISSION_CROSS_CHECK)
    script_msg.pop("pid", None)
    proto_msg = {k: v for k, v in proto_msg.items() if k != "pid"}
    assert script_msg == proto_msg


def test_embedded_codex_aliases_match_the_daemon_copy():
    """The embedded script duplicates CODEX_TOOL_ALIASES; the tables must be equal
    and every name must translate identically (the standalone script imports the
    daemon copy, so it cannot drift)."""
    from clawd_tank_daemon import codex_protocol
    from tests.test_codex_protocol import CODEX_ALIAS_CASES, CODEX_PASSTHROUGH
    namespace = {"__name__": "embedded_copy"}
    exec(compile(NOTIFY_SCRIPT, "<notify>", "exec"), namespace)
    assert namespace["CODEX_TOOL_ALIASES"] == codex_protocol.CODEX_TOOL_ALIASES
    for raw, expected in CODEX_ALIAS_CASES:
        assert namespace["_codex_tool"](raw) == expected
    for raw in [r for r, _ in CODEX_ALIAS_CASES] + CODEX_PASSTHROUGH + ["", "mcp__x__y"]:
        assert namespace["_codex_tool"](raw) == codex_protocol._codex_tool_name(raw)
