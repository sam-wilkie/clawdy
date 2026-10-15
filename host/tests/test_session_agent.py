from clawd_tank_daemon.daemon import _session_agent


def test_pi_session_ids_map_to_the_pi_product():
    assert _session_agent("pi:01a13c8c-19c4-75f2-a44d-72de40c81b18") == "pi"


def test_existing_prefixes_and_unprefixed_ids_are_unchanged():
    assert _session_agent("codex:abc") == "codex"
    assert _session_agent("kiro:abc") == "kiro"
    assert _session_agent("opencode:abc") == "opencode"
    assert _session_agent("antigravity:abc") == "antigravity"
    assert _session_agent("plain-claude-session") == "claude"
