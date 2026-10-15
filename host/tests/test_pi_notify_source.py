"""T3: the notify script accepts the `pi` source, standalone and embedded (S1, S7)."""

import importlib.machinery
import importlib.util
from pathlib import Path

from clawd_tank_menubar.hooks import NOTIFY_SCRIPT

HOST = Path(__file__).resolve().parents[1]


def _load_standalone():
    loader = importlib.machinery.SourceFileLoader("notify_standalone", str(HOST / "clawd-tank-notify"))
    spec = importlib.util.spec_from_file_location("notify_standalone", HOST / "clawd-tank-notify", loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_standalone_parses_pi_as_its_own_source():
    mod = _load_standalone()
    assert mod._parse_source(["pi"]) == "pi"


def test_standalone_translates_a_pi_payload_to_a_pi_session():
    mod = _load_standalone()
    msg = mod._translate_payload({"type": "agent_start", "sessionID": "x", "directory": "/w/p"}, "pi")
    assert msg["session_id"] == "pi:x"
    assert msg["event"] == "dismiss"


def test_embedded_script_defines_a_pi_translator():
    assert "def pi_hook_to_message(hook):" in NOTIFY_SCRIPT


def test_embedded_script_registers_a_pi_translator():
    assert '"pi": pi_hook_to_message' in NOTIFY_SCRIPT


def test_embedded_pi_translator_executes_like_the_daemon_one():
    # NOTIFY_SCRIPT is dedented, so the pi block sits at column 0.
    import clawd_tank_daemon.pi_protocol as daemon_side
    start = NOTIFY_SCRIPT.index("PI_SESSION_PREFIX = ")
    end = NOTIFY_SCRIPT.index("_AGENT_TRANSLATORS = {")
    ns = {"Path": Path, "_tool_summary": lambda name, args: "x"}
    exec(NOTIFY_SCRIPT[start:end], ns)
    hook = {"type": "agent_start", "sessionID": "e1", "directory": "/w/p"}
    assert ns["pi_hook_to_message"](hook) == daemon_side.pi_hook_payload_to_daemon_message(hook)


def _capture_standalone(decision, source):
    import contextlib
    import io
    mod = _load_standalone()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod._print_decision(decision, source)
    return buf.getvalue()


def test_standalone_pi_allow_prints_the_decision_the_extension_reads():
    assert _capture_standalone("allow", "pi") == '{"decision":"allow"}\n'


def test_standalone_pi_deny_prints_deny():
    assert _capture_standalone("deny", "pi") == '{"decision":"deny"}\n'


def test_standalone_pi_none_prints_nothing():
    assert _capture_standalone(None, "pi") == ""


def test_standalone_claude_keeps_hook_specific_output():
    out = _capture_standalone("allow", "claude")
    assert '"hookSpecificOutput"' in out and '"behavior":"allow"' in out


def test_embedded_pi_permission_prints_decision_json():
    import contextlib
    import io
    import json
    import sys
    ns = {"__name__": "embedded_check", "PERMISSION_DENY_MESSAGE": "no", "sys": sys, "json": json}
    start = NOTIFY_SCRIPT.index("def _print_decision(decision, agent):")
    body = NOTIFY_SCRIPT[start:]
    # Keep only this function: stop at the next top-level-or-method def after it.
    nxt = body.index("\n", body.index("sys.stdout.flush()"))
    import textwrap
    exec(textwrap.dedent(body[:nxt + 1]), ns)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ns["_print_decision"]("allow", "pi")
    assert buf.getvalue() == '{"decision":"allow"}\n'
