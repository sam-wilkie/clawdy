"""Tests for gating animation names by each transport's protocol version.

Protocol v3 firmware accepts "happy", "low_battery" and "hat_mishap" in
set_sessions. v2 firmware drops a slot whose animation name it doesn't know,
so the daemon must downgrade those names for v2 transports.
"""

import asyncio
import json
import time

import pytest
from unittest.mock import AsyncMock

import clawd_tank_daemon.daemon as daemon_mod
from clawd_tank_daemon.daemon import (
    MIN_PROTOCOL_FOR_PHASE1_ANIMS,
    PHASE1_ANIM_FALLBACKS,
    SIM_PROTOCOL_VERSION,
    ClawdDaemon,
    LOW_BATTERY_USAGE_PCT,
    downgrade_display_state,
)


class MockTransport:
    def __init__(self):
        self.is_connected = True
        self.written: list[str] = []

    async def write_notification(self, payload: str) -> None:
        self.written.append(payload)


def make_daemon(**versions):
    """Daemon with one MockTransport per keyword, at the given protocol version."""
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    transports = {}
    for name, version in versions.items():
        t = MockTransport()
        d._transports[name] = t
        d._transport_queues[name] = asyncio.Queue()
        d._transport_versions[name] = version
        transports[name] = t
    return d, transports


def _add_session(d, sid, state_dict):
    d._session_states[sid] = state_dict
    d._session_order.append((sid, d._next_display_id))
    d._next_display_id += 1


def sessions_of(transport):
    return [json.loads(p) for p in transport.written
            if json.loads(p).get("action") == "set_sessions"]


# --- Constants and the pure downgrade helper ---


def test_min_protocol_constant_is_three():
    assert MIN_PROTOCOL_FOR_PHASE1_ANIMS == 3


def test_fallback_mapping():
    assert PHASE1_ANIM_FALLBACKS == {
        "low_battery": "idle",
        "hat_mishap": "confused",
        "happy": "idle",
    }


def test_downgrade_maps_new_names_for_v2():
    state = {"anims": ["low_battery", "hat_mishap", "happy", "typing"],
             "ids": [1, 2, 3, 4], "subagents": 0}
    out = downgrade_display_state(state, 2)
    assert out["anims"] == ["idle", "confused", "idle", "typing"]
    assert out["ids"] == [1, 2, 3, 4]
    # The input is not mutated: other transports still need the original.
    assert state["anims"] == ["low_battery", "hat_mishap", "happy", "typing"]


def test_downgrade_keeps_new_names_for_v3():
    state = {"anims": ["low_battery", "hat_mishap", "happy"], "ids": [1, 2, 3], "subagents": 0}
    assert downgrade_display_state(state, 3) == state


def test_downgrade_passes_status_states_through():
    assert downgrade_display_state({"status": "sleeping"}, 2) == {"status": "sleeping"}


# --- Regular broadcasts ---


@pytest.mark.asyncio
async def test_v2_transport_gets_confused_instead_of_hat_mishap():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "WebFetch"})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "WebFetch"})
    assert sessions_of(t["ble"])[-1]["anims"] == ["confused"]
    assert not any("hat_mishap" in p for p in t["ble"].written)


@pytest.mark.asyncio
async def test_v3_transport_gets_hat_mishap():
    d, t = make_daemon(ble=3)
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "WebFetch"})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "WebFetch"})
    assert sessions_of(t["ble"])[-1]["anims"] == ["hat_mishap"]


@pytest.mark.asyncio
async def test_v2_transport_gets_idle_instead_of_low_battery():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": LOW_BATTERY_USAGE_PCT, "weekly_pct": 0}
    await d._broadcast_display_state_if_changed(force=True)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_mixed_transports_each_get_their_own_payload():
    d, t = make_daemon(ble=2, sim=3)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})
    d._latest_usage = {"session_pct": 0, "weekly_pct": LOW_BATTERY_USAGE_PCT + 5}
    await d._broadcast_display_state_if_changed(force=True)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle", "confused"]
    assert sessions_of(t["sim"])[-1]["anims"] == ["low_battery", "hat_mishap"]
    # The cached display state keeps the real (undowngraded) names.
    assert d._last_display_state["anims"] == ["low_battery", "hat_mishap"]


@pytest.mark.asyncio
async def test_v1_transport_still_gets_set_status_mapping():
    d, t = make_daemon(ble=1)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})
    await d._broadcast_display_state_if_changed(force=True)
    payloads = [json.loads(p) for p in t["ble"].written]
    assert payloads == [{"action": "set_status", "status": "confused"}]


# --- Oneshots ---


STOP_MSG = {"event": "add", "hook": "Stop", "session_id": "aaa",
            "project": "p", "message": "Waiting"}


@pytest.mark.asyncio
async def test_v2_transport_gets_no_happy_oneshot_on_end_of_turn():
    d, t = make_daemon(ble=2)
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    t["ble"].written.clear()

    await d._handle_message(dict(STOP_MSG))

    assert not any("happy" in p for p in t["ble"].written)
    # End of turn now rests in the waiting alert (Option B), not idle.
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_mixed_transports_happy_oneshot_only_on_v3():
    d, t = make_daemon(ble=2, sim=3)
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    for tr in t.values():
        tr.written.clear()

    await d._handle_message(dict(STOP_MSG))

    assert [s["anims"] for s in sessions_of(t["sim"])] == [["happy"], ["alert"]]
    assert not any("happy" in p for p in t["ble"].written)
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_v2_subagent_stop_sends_no_happy():
    d, t = make_daemon(ble=2)
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    t["ble"].written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})

    assert not any("happy" in p for p in t["ble"].written)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_v2_oneshot_downgrades_other_slots():
    """A oneshot every version knows still downgrades the other slots for v2."""
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time(), "tool_name": "WebFetch"})
    sent = await d._send_session_oneshot("s1", "alert")
    assert sent is True
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert", "confused"]


@pytest.mark.asyncio
async def test_v2_compact_sweep_downgrades_other_slots():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebFetch"})
    _add_session(d, "s2", {"state": "idle", "last_event": time.time()})
    await d._handle_message({"event": "compact", "session_id": "s2"})
    assert sessions_of(t["ble"])[0]["anims"] == ["confused", "sweeping"]
    assert not any("hat_mishap" in p for p in t["ble"].written)


# --- Post-connect sync / replay ---


@pytest.mark.asyncio
async def test_post_connect_replay_downgrades_for_v2_firmware(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(return_value=2)
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert d._transport_versions["ble"] == 2
    assert sessions_of(transport)[-1]["anims"] == ["confused"]


@pytest.mark.asyncio
async def test_post_connect_replay_keeps_new_names_for_v3_firmware(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(return_value=3)
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert sessions_of(transport)[-1]["anims"] == ["hat_mishap"]


@pytest.mark.asyncio
async def test_failed_version_read_defaults_to_v1(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(side_effect=RuntimeError("boom"))
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert d._transport_versions["ble"] == 1
    payloads = [json.loads(p) for p in transport.written]
    assert {"action": "set_status", "status": "confused"} in payloads
    assert not any(p.get("action") == "set_sessions" for p in payloads)


# --- Simulator ---


def test_simulator_is_treated_as_v3():
    assert SIM_PROTOCOL_VERSION == 3
    d, _ = make_daemon()
    d._on_transport_connect("sim")
    assert d._transport_versions["sim"] == 3


# --- Phase 2 products downgrade ---


def test_ble_payload_strips_pet_only_fields_but_sim_keeps_them():
    """agents/products are desktop-pet-only (Phase 1-2). The ESP firmware ignores
    them AND its GATT char rejects a write past the MTU, so these fields must be
    stripped for the BLE transport (which nearly doubled the JSON and broke writes
    with WinError E_INVALIDARG). The 'sim' transport (the Electron pet) keeps them.
    """
    d, t = make_daemon(ble=3, sim=3)
    _add_session(d, "c1", {"state": "working", "last_event": time.time()})
    _add_session(d, "kiro:k1", {"state": "thinking", "last_event": time.time()})
    state = d._compute_display_state()
    assert "products" in state and "agents" in state  # present at source

    ble = json.loads(d._set_sessions_payload_for("ble", state))
    sim = json.loads(d._set_sessions_payload_for("sim", state))

    # ESP: no pet-only fields, but still gets the per-slot anims/ids it reads.
    assert "products" not in ble and "agents" not in ble
    assert ble["anims"] and ble["ids"]
    # Pet: keeps the per-product aggregation it renders.
    assert "products" in sim and "agents" in sim


def test_downgrade_rewrites_v2_only_names_inside_products():
    """The per-product crabs (Phase 2) carry their own anim name, so a v2
    transport must get those names downgraded too — otherwise its parser drops
    the slot. v3 keeps them unchanged."""
    state = {
        "anims": ["hat_mishap"],
        "ids": [1],
        "agents": ["claude"],
        "products": [{"agent": "claude", "count": 1, "anim": "hat_mishap"}],
        "subagents": 0,
    }
    v2 = downgrade_display_state(state, 2)
    assert v2["products"] == [{"agent": "claude", "count": 1, "anim": "confused"}]
    assert v2["anims"] == ["confused"]
    # Original is never mutated; v3 passes through unchanged.
    assert state["products"][0]["anim"] == "hat_mishap"
    assert downgrade_display_state(state, 3) is state


def test_bg_is_pet_only_and_survives_downgrade_without_breaking_v2():
    """products[].bg feeds the desktop pet only: BLE never sees it (payload stays
    small), a v2 transport's per-slot anim names are still valid, and downgrading
    keeps bg for the pet."""
    d, _ = make_daemon(ble=2, sim=3)
    _add_session(d, "c1", {"state": "idle", "last_event": time.time(), "subagents": {"a", "b"}})
    state = d._compute_display_state()
    assert state["products"][0]["bg"] == 2

    ble = d._set_sessions_payload_for("ble", state)
    assert "bg" not in ble and "products" not in ble
    assert len(ble.encode()) < 200
    assert json.loads(ble)["anims"] == ["conducting"]  # v2 knows conducting

    sim = json.loads(d._set_sessions_payload_for("sim", state))
    assert sim["products"][0]["bg"] == 2

    v2 = downgrade_display_state(state, 2)
    assert v2["products"][0]["bg"] == 2
    assert v2["products"][0]["anim"] == "conducting"


# --- End-of-turn "waiting_reply": only the Electron desktop pet has the art ---
#
# The daemon reports an end-of-turn wait (Stop / idle_prompt) as "waiting_reply"
# and a blocked wait (PermissionRequest / AskUserQuestion) as "alert". Firmware
# and the SDL2 simulator have no "waiting_reply" sprite (v2/v3 firmware drops a
# slot it does not know), so every transport except the desktop pet gets "alert".


def make_daemon_with_pet(**versions):
    """Like make_daemon, plus a v3 "sim" transport that is the desktop pet."""
    d, t = make_daemon(**versions)
    pet = MockTransport()
    pet.desktop_pet = True
    d._transports["sim"] = pet
    d._transport_queues["sim"] = asyncio.Queue()
    d._transport_versions["sim"] = SIM_PROTOCOL_VERSION
    t["sim"] = pet
    return d, t


async def _start_turn(d, sid="aaa"):
    await d._handle_message({"event": "session_start", "session_id": sid})
    await d._handle_message({"event": "tool_use", "session_id": sid, "tool_name": "Bash"})


@pytest.mark.asyncio
async def test_stop_sends_waiting_reply_to_pet_and_alert_to_ble():
    d, t = make_daemon_with_pet(ble=3, ble_old=2)
    await _start_turn(d)
    await d._handle_message(dict(STOP_MSG))

    pet = sessions_of(t["sim"])[-1]
    assert pet["anims"] == ["waiting_reply"]
    assert pet["products"][0]["anim"] == "waiting_reply"
    for name in ("ble", "ble_old"):
        assert sessions_of(t[name])[-1]["anims"] == ["alert"], name
        assert not any("waiting_reply" in p for p in t[name].written), name


@pytest.mark.asyncio
async def test_sdl_simulator_gets_alert_not_waiting_reply():
    """A "sim" transport that is NOT the desktop pet (the SDL2 window) shares
    the firmware's sprite set, so it gets alert in anims and products."""
    d, t = make_daemon(sim=SIM_PROTOCOL_VERSION)
    await _start_turn(d)
    await d._handle_message(dict(STOP_MSG))
    last = sessions_of(t["sim"])[-1]
    assert last["anims"] == ["alert"]
    assert last["products"][0]["anim"] == "alert"
    assert not any("waiting_reply" in p for p in t["sim"].written)


@pytest.mark.asyncio
async def test_idle_prompt_sends_waiting_reply_to_pet_only():
    d, t = make_daemon_with_pet(ble=3)
    await _start_turn(d)
    await d._handle_message({"event": "add", "hook": "Notification", "session_id": "aaa",
                             "project": "p", "message": "Claude is waiting for your input"})
    assert sessions_of(t["sim"])[-1]["anims"] == ["waiting_reply"]
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert"]


@pytest.mark.asyncio
@pytest.mark.parametrize("blocking", [
    {"event": "permission", "session_id": "aaa", "tool_name": "Bash"},
    {"event": "tool_use", "session_id": "aaa", "tool_name": "AskUserQuestion"},
])
async def test_blocked_waits_send_alert_everywhere(blocking):
    d, t = make_daemon_with_pet(ble=3)
    await _start_turn(d)
    await d._handle_message(dict(blocking))
    assert sessions_of(t["sim"])[-1]["anims"] == ["alert"]
    assert sessions_of(t["sim"])[-1]["products"][0]["anim"] == "alert"
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert"]


@pytest.mark.asyncio
async def test_v1_transport_reads_waiting_reply_as_needs_attention():
    """v1 aggregates to one status; the end-of-turn wait maps like alert did."""
    d, t = make_daemon(ble=1)
    await _start_turn(d)
    await d._handle_message(dict(STOP_MSG))
    payloads = [json.loads(p) for p in t["ble"].written
                if json.loads(p).get("action") == "set_status"]
    assert payloads[-1] == {"action": "set_status", "status": "confused"}
