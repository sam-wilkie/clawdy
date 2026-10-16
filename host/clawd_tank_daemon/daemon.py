"""Clawd Tank daemon — bridges Claude Code hooks to ESP32 via BLE."""

import asyncio
import hmac
import json
import logging
import os
import secrets
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from .ble_client import ClawdBleClient
from .claude_usage import ClaudeUsageReader
from .codex_usage import CodexUsageReader
from .opencode_usage import OpenCodeUsageReader
from .pi_usage import PiUsageReader
from .usage_export import build_document, write_json_atomic
from .kiro_log_watcher import run_kiro_log_watcher
from .process_utils import pid_alive, terminate_pid
from .protocol import (
    ASK_USER_QUESTION_TOOL,
    PERMISSION_WAIT_SECONDS,
    daemon_message_to_ble_payload,
    display_state_to_ble_payload,
    display_state_to_v1_payload,
    project_usage_to_payload,
    read_usage_from_cache,
    usage_to_ble_payload,
)
from .sim_client import SimClient, SIM_DEFAULT_PORT
from .socket_server import SocketServer
from .transport import TransportClient
from . import session_store
from . import single_instance
from .session_store import save_sessions, load_sessions

logger = logging.getLogger("clawd-tank")

TOOL_ANIMATION_MAP = {
    "Edit": "typing",
    "Write": "typing",
    "NotebookEdit": "typing",
    "Read": "debugger",
    "Grep": "debugger",
    "Glob": "debugger",
    "Bash": "building",
    "Agent": "conducting",
    "WebSearch": "wizard",
    "WebFetch": "wizard",
    "LSP": "beacon",
}


# Tools whose failure shows "hat_mishap" (the wizard hat falls over the crab's
# eyes) instead of the generic "confused". They are the tools that show "wizard".
WEB_TOOLS = frozenset({"WebSearch", "WebFetch"})

# An idle crab shows "low_battery" once the 5h or weekly usage reaches this
# percentage: little headroom is left before the rate limit.
LOW_BATTERY_USAGE_PCT = 90

# Protocol v3 firmware accepts these animations in set_sessions. v2 firmware's
# parser returns -1 for a name it doesn't know and drops that slot, so the crab
# vanishes; for those transports the names are swapped for the closest
# animation v2 knows. "happy" as a oneshot is skipped instead (see
# _send_session_oneshot); the mapping only covers it in a regular state.
MIN_PROTOCOL_FOR_PHASE1_ANIMS = 3
PHASE1_ANIM_FALLBACKS = {
    "low_battery": "idle",
    "hat_mishap": "confused",
    "happy": "idle",
}

# Animations only the Electron desktop pet has art for. Firmware and the SDL2
# simulator share one sprite set without them (v2/v3 firmware drops a slot with
# an unknown name), so every other transport gets the fallback, whatever its
# protocol version. "waiting_reply" is the calm end-of-turn wait; hardware keeps
# showing it as the urgent "alert", exactly as before the split.
DESKTOP_PET_ANIM_FALLBACKS = {
    "waiting_reply": "alert",
}

# The simulator compiles the same firmware sources, so it speaks the latest
# protocol. It has no version characteristic to read.
SIM_PROTOCOL_VERSION = 3

# Wait for the user's decision or the hook/session to close.
PERMISSION_DAEMON_WAIT_SECONDS = PERMISSION_WAIT_SECONDS
PERMISSION_DECISIONS = ("allow", "deny")
# Defensive caps on what is shown in the bubble (the hook already truncates).
_PERMISSION_FIELD_MAX = {"project": 64, "tool": 64, "summary": 120}


def downgrade_display_state(state: dict, version: int) -> dict:
    """Return `state` with the animation names a `version` transport understands.

    The input is never mutated (other transports may still need the original
    names); a status-only state, or a transport at MIN_PROTOCOL_FOR_PHASE1_ANIMS
    or newer, gets `state` back unchanged."""
    if version >= MIN_PROTOCOL_FOR_PHASE1_ANIMS:
        return state
    return _map_anims(state, PHASE1_ANIM_FALLBACKS)


def _map_anims(state: dict, fallbacks: dict) -> dict:
    """Return `state` with every animation name in `fallbacks` replaced.

    The input is never mutated; a status-only state is returned unchanged. The
    per-product crabs (Phase 2) carry their own anim name, so they get the same
    fallback or a transport would receive a name its parser drops."""
    if "anims" not in state:
        return state
    mapped = {**state, "anims": [fallbacks.get(a, a) for a in state["anims"]]}
    if "products" in state:
        mapped["products"] = [
            {**p, "anim": fallbacks.get(p["anim"], p["anim"])}
            for p in state["products"]
        ]
    return mapped


# Tool events that, when tagged with an agent_id, belong to a subagent rather
# than to the session's main agent (see _update_session_state).
SUBAGENT_TOOL_EVENTS = ("tool_use", "tool_done", "tool_failed")


def _tool_to_anim(tool_name: str) -> str:
    if tool_name and tool_name.startswith("mcp__"):
        return "beacon"
    return TOOL_ANIMATION_MAP.get(tool_name, "typing")


def _state_to_anim(state: dict, has_subagents: bool, usage_low: bool) -> str:
    """Animation name for one session's state.

    The crab shows what the session itself is doing; its subagents are reported
    by the HUD counter. 'conducting' is only for a session that is idle while its
    subagents work, so the crab doesn't freeze on it while the main session keeps
    thinking and running tools. Shared by the per-slot list and the per-product
    aggregation so both pick the same animation for a given state.
    """
    s = state["state"]
    if s == "waiting":
        # Same state, two meanings: the turn ended and the session awaits the
        # next prompt (calm), or it is blocked on an approval/answer (urgent).
        return "waiting_reply" if state.get("awaiting_prompt") else "alert"
    if s == "working":
        return _tool_to_anim(state.get("tool_name", ""))
    if s == "thinking":
        return "thinking"
    if s == "confused":
        return "hat_mishap" if state.get("tool_name") in WEB_TOOLS else "confused"
    if s == "error":
        return "dizzy"
    if s == "out_of_credits":
        # Reuses the low-battery crab (v2 transports downgrade it to idle); the
        # "Out of credits" card carries the actual message.
        return "low_battery"
    if has_subagents:
        return "conducting"
    if usage_low:
        return "low_battery"
    return "idle"


# Which AI product a session belongs to, derived from the session-id prefix the
# translators add (codex_protocol "codex:", kiro_protocol "kiro:",
# opencode_protocol "opencode:", antigravity_protocol "antigravity:", Claude
# none). Grouped by PRODUCT: a Kiro IDE session and a Kiro CLI session are both
# "kiro", and the agy CLI and the Antigravity IDE are both "antigravity". Lets the desktop pet pick a
# per-product crab (and group/count by product) without the daemon storing
# anything new — the prefix is the single source of truth. Unknown/unprefixed
# ids are Claude Code, the original agent.
SESSION_AGENT_PREFIXES = (
    ("codex:", "codex"),
    ("kiro:", "kiro"),
    ("opencode:", "opencode"),
    ("antigravity:", "antigravity"),
    ("pi:", "pi"),
)


def _session_agent(session_id: str) -> str:
    """Return the product name for a (possibly namespaced) session id."""
    for prefix, agent in SESSION_AGENT_PREFIXES:
        if session_id.startswith(prefix):
            return agent
    return "claude"


# Path to the per-product preference file used by both the menubar app and the
# daemon. PR1 adds `enable_opencode` here; existing keys (`ble_enabled`,
# `sim_enabled`, `sim_window_visible`, `sim_always_on_top`, `sim_desk_mode`,
# preferences) live in clawd_tank_menubar.preferences but the daemon
# only reads the keys it cares about.
_PREFERENCES_PATH = Path.home() / ".clawd-tank" / "preferences.json"


def _load_preferences() -> dict:
    """Read the preferences file. Missing/unparseable files behave as empty,
    so the daemon defaults (enable_opencode True) apply."""
    try:
        text = _PREFERENCES_PATH.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# Priority of each animation when several sessions of the SAME product are
# collapsed into one per-product crab (Phase 2 xN grouping). The product crab
# shows its most actionable session: "needs you" (alert) outranks active work,
# which outranks thinking, which outranks the end-of-turn wait, which outranks
# error/confused states, which outrank an idle-but-conducting crab, which outranks
# a plain resting crab. Any anim not listed (future additions) sorts at 0, below
# everything explicit here.
_ANIM_PRIORITY = {
    "alert": 100,
    # Active work — all equal; the specific tool anim is kept as-is. It outranks
    # the end-of-turn wait so a session that finished its turn cannot hide a
    # sibling that is still running (the crab would otherwise look idle).
    "typing": 90, "building": 90, "debugger": 90, "wizard": 90,
    "beacon": 90, "sweeping": 90,
    "thinking": 60,
    # End-of-turn wait: "your turn", but calm, so it yields to any active sibling.
    "waiting_reply": 55,
    "hat_mishap": 40, "confused": 40, "dizzy": 40,
    "conducting": 20,
    "low_battery": 10,
    "idle": 5,
}


def _aggregate_products(agents: list, anims: list, bgs: Optional[list] = None,
                        exhausted: Optional[list] = None) -> list:
    """Collapse parallel (agent, anim) slots into one entry per product.

    Returns a list of {"agent", "count", "anim"} dicts, one per distinct
    product, in first-seen order (so the layout stays stable as sessions come
    and go). `count` is how many sessions that product has among these slots;
    `anim` is the highest-priority animation across them (see _ANIM_PRIORITY),
    i.e. the product crab reflects its most actionable session.

    `bgs` (parallel to the slots) is how many subagents each session has running;
    a product's "bg" is their sum, emitted only when > 0 so payloads without
    subagents are unchanged. Only the desktop pet reads it (to show 'grooving'
    while subagents work); it never alters `anim`, which hardware also sees.

    `exhausted` (parallel to the slots) flags sessions in the out_of_credits
    state, which `anim` reports as plain "low_battery" for hardware. A product
    gets "exhausted": True (omitted otherwise, like "bg") only when one of its
    sessions is out of credits AND the product's final `anim` is still
    "low_battery": any more actionable sibling (alert, work, thinking, error,
    subagents/conducting; all outrank low_battery in _ANIM_PRIORITY) keeps the
    pet on that, and the broke crab returns once nothing else needs attention.
    Only the desktop pet reads it; `anim` is never altered.
    """
    order = []
    by_agent = {}
    bgs = bgs if bgs is not None else [0] * len(agents)
    exhausted = exhausted if exhausted is not None else [False] * len(agents)
    broke = set()
    for agent, anim, bg, spent in zip(agents, anims, bgs, exhausted):
        if spent:
            broke.add(agent)
        entry = by_agent.get(agent)
        if entry is None:
            entry = {"agent": agent, "count": 0, "anim": anim}
            by_agent[agent] = entry
            order.append(agent)
        entry["count"] += 1
        if bg:
            entry["bg"] = entry.get("bg", 0) + bg
        if _ANIM_PRIORITY.get(anim, 0) > _ANIM_PRIORITY.get(entry["anim"], 0):
            entry["anim"] = anim
    for agent in broke:
        if by_agent[agent]["anim"] == "low_battery":
            by_agent[agent]["exhausted"] = True
    return [by_agent[a] for a in order]


PID_PATH = Path.home() / ".clawd-tank" / "daemon.pid"
LOCK_PATH = Path.home() / ".clawd-tank" / "daemon.lock"
# After stopping the old daemon on takeover, keep retrying the lock this long.
# On Windows the OS releases a terminated process's lock slightly after the
# process exits, so a single immediate retry fails.
LOCK_TAKEOVER_TIMEOUT_SECS = 3.0
LOCK_RETRY_STEP_SECS = 0.1
# Cache written by the statusLine bridge (hooks.STATUSLINE_BRIDGE_SH on macOS/Linux,
# hooks.STATUSLINE_BRIDGE_SCRIPT on Windows, installed as ~/.clawd-tank/
# statusline_bridge.sh / .py) holding Claude Code's rate_limits.
USAGE_CACHE_PATH = str(Path.home() / ".clawd-tank" / "statusline-cache.json")
# How often to poll the usage cache and push set_usage to transports.
USAGE_POLL_INTERVAL_SECS = 15.0
PROJECT_USAGE_POLL_INTERVAL_SECS = 60.0
PID_DEDUP_FRESHNESS_SECONDS = 60.0
# How often to actively probe BLE links for liveness. macOS CoreBluetooth often
# never reports range/sleep disconnects, so without this probe a dead link is
# never detected and the daemon never re-scans. Detection lag ~= this interval.
BLE_LIVENESS_INTERVAL_SECS = 20.0
# How often an idle transport sender checks that its link is still up (and
# reconnects it if not). Detection lag for a dropped link ~= this interval.
SENDER_IDLE_POLL_SECS = 1.0
# A transport sender that crashes is restarted after base * 2**n seconds, capped
# at the maximum; a sender that then runs for SENDER_STABLE_SECS without
# crashing starts the back-off over. Without a restart one stray exception left
# the transport with no sender: no automatic reconnect, queue never drained.
SENDER_RESTART_BASE_SECS = 1.0
SENDER_RESTART_MAX_SECS = 30.0
SENDER_STABLE_SECS = 60.0
# How often to check that each session's Claude Code process is still alive. A
# window closed with the X sends no SessionEnd, so this interval is how long its
# crab lingers. A PID check is a cheap OS call, so keep it short.
PID_LIVENESS_INTERVAL_SECS = 5.0
# Sessions WITHOUT a resolvable PID (e.g. a node-hosted Claude Code on Windows,
# where the hook finds no claude.exe ancestor) can't be pruned by the PID-liveness
# checker. They rely entirely on time-based eviction, so they use a much
# shorter timeout than PID-backed sessions (which the liveness checker evicts
# the instant the process dies). Keeps ghost sessions from lingering ~10 min
# after a terminal is closed. Applies identically on macOS and Windows.
NO_PID_STALENESS_TIMEOUT = 90.0
# States in which a session seen in Kiro's log keeps the normal staleness
# timeout despite having no PID: an opened-but-unused Kiro (registered) or one
# that hit its usage limit (out_of_credits) legitimately sends no events.
LOG_RESTING_STATES = ("registered", "out_of_credits")


@runtime_checkable
class DaemonObserver(Protocol):
    def on_connection_change(self, connected: bool, transport: str = "") -> None: ...
    def on_notification_change(self, count: int) -> None: ...


def _stop_existing_daemon() -> bool:
    """Send SIGTERM to an existing daemon and wait for it to exit. Returns True if stopped."""
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
    except (ValueError, OSError):
        return False
    try:
        # On Windows this is TerminateProcess, not SIGTERM, so the old
        # daemon's _shutdown() never runs. Its lock and PID file are still
        # released by the OS; a graceful stop needs an IPC request instead.
        terminate_pid(pid)
    except ProcessLookupError:
        return True  # already dead
    except PermissionError:
        return False
    # Wait up to 3 seconds for it to release the lock
    import time
    for _ in range(30):
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    logger.warning("Existing daemon (PID %d) did not exit in time", pid)
    return False


def _acquire_lock(takeover: bool = False) -> int:
    """Acquire an exclusive file lock.

    If takeover is True (menu bar mode), stop the existing daemon first.
    If takeover is False (headless mode), exit if another daemon is running.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = single_instance.acquire(LOCK_PATH)
    except OSError:
        if takeover:
            logger.info("Stopping existing daemon to take over...")
            _stop_existing_daemon()
            fd = _retry_lock_after_takeover()
        else:
            print("Another clawd-tank daemon is already running", file=sys.stderr)
            sys.exit(0)
    return fd


def _retry_lock_after_takeover() -> int:
    """Retry the lock until LOCK_TAKEOVER_TIMEOUT_SECS; exit(1) on failure."""
    attempts = round(LOCK_TAKEOVER_TIMEOUT_SECS / LOCK_RETRY_STEP_SECS)
    for attempt in range(attempts + 1):
        try:
            return single_instance.acquire(LOCK_PATH)
        except OSError:
            if attempt < attempts:
                time.sleep(LOCK_RETRY_STEP_SECS)
    message = "Could not acquire lock after stopping existing daemon"
    logger.error("%s (waited %ss)", message, LOCK_TAKEOVER_TIMEOUT_SECS)
    print(message, file=sys.stderr)
    sys.exit(1)


class ClawdDaemon:
    def __init__(
        self,
        observer: Optional["DaemonObserver"] = None,
        headless: bool = True,
        sim_port: int = 0,
        sim_only: bool = False,
        sessions_path: Optional[Path] = None,
        ble_enabled: bool = True,
        sim_desktop_pet: bool = False,
        startup=None,
    ):
        self._transports: dict[str, TransportClient] = {}
        self._transport_queues: dict[str, asyncio.Queue] = {}

        if headless:
            # Headless (CLI) mode — create transports from args
            if not sim_only and ble_enabled:
                ble = ClawdBleClient(
                    on_disconnect_cb=lambda: self._on_transport_disconnect("ble"),
                    on_connect_cb=lambda: self._on_transport_connect("ble"),
                )
                self._transports["ble"] = ble
                self._transport_queues["ble"] = asyncio.Queue()

            if sim_port > 0:
                sim = SimClient(
                    port=sim_port,
                    on_disconnect_cb=lambda: self._on_transport_disconnect("sim"),
                    on_connect_cb=lambda: self._on_transport_connect("sim"),
                    on_event_cb=self.handle_sim_event,
                    desktop_pet=sim_desktop_pet,
                )
                self._transports["sim"] = sim
                self._transport_queues["sim"] = asyncio.Queue()
        # Menu bar mode (headless=False): transports added later via add_transport()

        self._sender_tasks: dict[str, asyncio.Task] = {}
        # Permission requests waiting on a desk-window decision, by request id:
        # {id, nonce, session_id, future, created}. Routing is strictly by id.
        self._pending_permissions: dict[str, dict] = {}
        self._socket = SocketServer(on_message=self._handle_message)
        self._active_notifications: dict[str, dict] = {}
        self._last_usage_key: Optional[tuple] = None
        # Latest {session_pct, weekly_pct, reset_seconds} read from the usage
        # cache; drives the "low_battery" idle animation.
        self._latest_usage: Optional[dict] = None
        # Per-project token/cost usage, read from ~/.claude and sent only to
        # desktop_pet transports. The cached payload is replayed on connect.
        self._project_usage_reader = ClaudeUsageReader(Path.home() / ".claude" / "projects")
        self._project_usage_readers = {
            "claude": self._project_usage_reader,
            "codex": CodexUsageReader(Path.home() / ".codex" / "sessions"),
            "opencode": OpenCodeUsageReader(Path.home() / ".local" / "share" / "opencode" / "opencode.db"),
            "pi": PiUsageReader(Path.home() / ".pi" / "agent" / "sessions"),
        }
        self._project_usage_path = Path.home() / ".clawd-tank" / "project-usage.json"
        self._project_usage_document = None
        self._project_usage_payload: Optional[str] = None
        self._running = True
        self._shutdown_event = asyncio.Event()
        self._lock_fd: int | None = None
        self._observer = observer
        self._headless = headless
        # Callable run once after the daemon lock is won (hook install); None skips it.
        self._startup = startup
        self._sessions_path = sessions_path if sessions_path is not None else session_store.SESSIONS_PATH
        # Per-product preference gate: a user can keep the OpenCode plugin
        # installed while still suppressing its events (debugging, switching
        # products). New in PR1 — Codex/Kiro have no equivalent. Default is
        # True so an unset preferences file behaves identically to before.
        self._preferences = _load_preferences()
        loaded_states, loaded_order, loaded_next_id = load_sessions(self._sessions_path)

        # One-shot startup prune by wall-clock: if last_event is older than the
        # staleness timeout, the session almost certainly belongs to a dead Claude
        # Code process from before the daemon restarted. After this prune we switch
        # to monotonic time for runtime tracking (survives macOS sleep/wake).
        now_wall = time.time()
        stale_ids = [
            sid for sid, s in loaded_states.items()
            # Same adaptive rule as runtime eviction: sessions without a PID
            # (all persisted sessions, since PID isn't serialized) expire on the
            # short timeout; PID-backed ones keep the long default.
            if now_wall - s.get("last_event", now_wall) >
               (600.0 if s.get("pid") is not None else NO_PID_STALENESS_TIMEOUT)
        ]
        for sid in stale_ids:
            del loaded_states[sid]
        loaded_order = [(sid, did) for sid, did in loaded_order if sid not in stale_ids]

        now_mono = time.monotonic()
        for state in loaded_states.values():
            state["last_event_monotonic"] = now_mono
        self._session_states: dict[str, dict] = loaded_states
        self._session_order: list[tuple[str, int]] = loaded_order
        self._next_display_id: int = loaded_next_id
        self._last_display_state: dict = {"status": "sleeping"}
        self._transport_versions: dict[str, int] = {}  # transport_name → protocol version
        self._session_staleness_timeout: float = 600.0
        # _evict_stale_sessions() removed — Task 6 startup prune covers this.

    async def _handle_message(self, msg: dict, reply=None) -> None:
        """Handle a message from clawd-tank-notify via the socket.

        `reply` is only given for a message that asked to wait ("wait": true); it
        is the socket server WaitReply for that client."""
        event = msg.get("event")
        session_id = msg.get("session_id", "")
        hook = msg.get("hook", "")
        from_log = bool(msg.get("from_log"))
        # PR1: per-product preference gate for `enable_opencode`. When the user
        # has disabled OpenCode plugin events, drop every opencode:-prefixed
        # message before any state work — same effect as if the plugin were
        # not installed. Codex/Kiro have no equivalent gate (verified by
        # absence in clawd_tank_menubar.preferences).
        if (session_id.startswith("opencode:")
                and not self._preferences.get("enable_opencode", True)):
            return
        if event == "session_heartbeat":
            # A heartbeat is liveness, not a new tool or an approval answer.
            # Preserve the current state (especially a pending permission).
            if not session_id.startswith("opencode:"):
                return
            state = self._session_states.get(session_id)
            if state is None:
                snapshot = msg.get("state")
                if snapshot not in ("registered", "thinking", "working", "waiting"):
                    return
                state = {"state": snapshot, "project": msg.get("project", ""),
                         "tool_name": msg.get("tool_name", "")}
                if snapshot == "waiting":
                    state["awaiting_prompt"] = True
                self._session_states[session_id] = state
                if session_id not in [sid for sid, _ in self._session_order]:
                    self._session_order.append((session_id, self._next_display_id))
                    self._next_display_id += 1
            state["last_event"] = time.time()
            state["last_event_monotonic"] = time.monotonic()
            self._persist_sessions()
            await self._broadcast_display_state_if_changed()
            return
        # Kiro's log reports a new session that a hook may already have
        # registered; re-registering it would reset its state.
        if from_log and event == "session_start" and session_id in self._session_states:
            return
        # Activity from a session means whatever it was blocked on is resolved
        # (answered in the terminal, turn ended, ...): drop its open requests.
        if session_id and (
            event in ("tool_use", "tool_done")
            or (event == "add" and hook == "Stop")
            or (event == "dismiss" and hook in ("UserPromptSubmit", "SessionEnd"))
        ):
            self._cancel_session_permissions(session_id)
        # Store project name on session if provided
        project = msg.get("project", "")
        # A translator-flagged fallback title (e.g. a product name used when no
        # workspace is known) must never replace a real project already stored.
        project_is_fallback = bool(msg.get("project_fallback"))
        if project and session_id and session_id in self._session_states:
            if not (project_is_fallback
                    and self._session_states[session_id].get("project")):
                self._session_states[session_id]["project"] = project
        elif project and session_id:
            # Will be stored after _update_session_state creates the entry
            pass

        extra = ""
        if event in ("tool_use", "tool_done", "permission", "tool_failed"):
            extra = f" tool={msg.get('tool_name', '?')}"
        elif event in ("subagent_start", "subagent_stop"):
            extra = f" agent={msg.get('agent_id', '?')[:12]}"
        elif event == "add":
            extra = f" msg={msg.get('message', '')[:30]}"
        if msg.get("source"):
            extra += f" source={msg['source']}"
        if msg.get("reason"):
            extra += f" reason={msg['reason']}"
        if msg.get("pid"):
            extra += f" pid={msg['pid']}"
        session_project = ""
        if session_id:
            s = self._session_states.get(session_id)
            if s and s.get("project"):
                session_project = f" [{s['project']}]"
            elif project:
                session_project = f" [{project}]"
        logger.info("Socket msg: event=%s hook=%s session=%s%s%s",
                     event, hook, session_id[:12], session_project, extra)

        # End of turn (Stop) is shown by the crab (a happy oneshot), and Claude
        # Code's idle_prompt ("waiting for your input") just leaves it idle.
        # Neither gets a notification card: cards are for things the user must
        # act on, such as API errors.
        end_of_turn = event == "add" and hook == "Stop"
        no_card = end_of_turn or (event == "add" and hook == "Notification")
        if event == "add" and not no_card:
            self._active_notifications[session_id] = msg
        elif event == "dismiss":
            self._active_notifications.pop(session_id, None)

        # --- PID-based dedup: SessionStart with PID matching a recent session = /clear ---
        if event == "session_start":
            incoming_pid = msg.get("pid")
            if incoming_pid is not None:
                now_mono = time.monotonic()
                to_evict = []
                for sid, state in self._session_states.items():
                    if sid == session_id:
                        continue
                    if state.get("pid") != incoming_pid:
                        continue
                    last_mono = state.get("last_event_monotonic", now_mono)
                    if now_mono - last_mono < PID_DEDUP_FRESHNESS_SECONDS:
                        to_evict.append(sid)
                for sid in to_evict:
                    logger.info(
                        "PID dedup: evicting session %s (PID %d reused by new session %s)",
                        sid[:12], incoming_pid, session_id[:12],
                    )
                    del self._session_states[sid]
                    self._session_order = [(s, d) for s, d in self._session_order if s != sid]
                    self._active_notifications.pop(sid, None)

        changed = self._update_session_state(
            event, hook, session_id,
            msg.get("agent_id", ""), msg.get("tool_name", ""),
            pid=msg.get("pid"),
            exhausted=bool(msg.get("exhausted")),
        )

        # Store project name after session state is created
        if project and session_id and session_id in self._session_states:
            if not (project_is_fallback
                    and self._session_states[session_id].get("project")):
                self._session_states[session_id]["project"] = project
        if from_log and session_id in self._session_states:
            self._session_states[session_id]["log_seen"] = True

        # --- Handle compact: send sweeping oneshot ---
        if event == "compact":
            computed = self._compute_display_state()
            for name, transport in self._transports.items():
                if not transport.is_connected:
                    continue
                version = self._transport_versions.get(name, 1)
                if version >= 2 and session_id:
                    # V2: send set_sessions with the compacting session's slot as "sweeping"
                    sweeping_state = self._compute_display_state()
                    if "anims" in sweeping_state:
                        for sid, did in self._session_order:
                            if sid == session_id:
                                idx = next(
                                    (i for i, d in enumerate(sweeping_state["ids"]) if d == did),
                                    None,
                                )
                                if idx is not None:
                                    sweeping_state["anims"][idx] = "sweeping"
                                break
                    payload = self._set_sessions_payload_for(name, sweeping_state)
                    await transport.write_notification(payload)
                    # No second fallback for v2 — firmware handles sweeping as oneshot
                else:
                    # V1: send sweeping oneshot then restore display state
                    sweeping_payload = json.dumps({"action": "set_status", "status": "sweeping"})
                    await transport.write_notification(sweeping_payload)
                    fallback_payload = display_state_to_v1_payload(computed)
                    await transport.write_notification(fallback_payload)
            self._last_display_state = computed

        # --- Handle subagent finished: celebrate on the parent's slot ---
        celebrated = False
        if (event == "subagent_stop" and changed) or end_of_turn:
            celebrated = await self._send_session_oneshot(session_id, "happy")

        if not no_card:
            for q in self._transport_queues.values():
                await q.put(msg)

        if self._observer:
            self._observer.on_notification_change(len(self._active_notifications))

        if event != "compact":
            # After a oneshot, always re-send the real state: the firmware keeps
            # it as the slot's fallback and returns to it when the oneshot ends.
            await self._broadcast_display_state_if_changed(force=celebrated)

        if changed:
            self._persist_sessions()

        if event == "permission" and msg.get("wait") is True and reply is not None:
            await self._wait_for_permission(msg, reply)

    # --- Permission bubble (desk window decides, hook waits) -----------------

    def _connected_sim_names(self) -> list[str]:
        """Simulator transports that are up and have a queue. Only these may
        show the bubble; BLE devices never see permission traffic."""
        return [
            name for name, t in self._transports.items()
            if name.startswith("sim") and t.is_connected and name in self._transport_queues
        ]

    def _enqueue_to_sims(self, item: dict) -> None:
        for name in self._connected_sim_names():
            self._transport_queues[name].put_nowait(item)

    async def _wait_for_permission(self, msg: dict, reply) -> None:
        """Ask the desk window to approve a tool and answer the waiting hook.

        Ends with at most one reply: "allow" or "deny" only for an explicit valid
        decision, "none" for every other outcome (no simulator, timeout, hook
        hung up, cleanup, shutdown)."""
        if not self._connected_sim_names():
            await reply.send({"decision": "none"})
            return
        request_id = uuid.uuid4().hex
        nonce = secrets.token_hex(8)
        future = asyncio.get_running_loop().create_future()
        self._pending_permissions[request_id] = {
            "id": request_id,
            "nonce": nonce,
            "session_id": msg.get("session_id", ""),
            "future": future,
            "created": time.monotonic(),
        }
        fields = {
            "project": msg.get("project"),
            "tool": msg.get("tool_name"),
            "summary": msg.get("tool_summary"),
        }
        request = {
            "event": "permission_request",
            "id": request_id,
            "nonce": nonce,
            # Which product asked, so the desktop pet can show the bubble over
            # that product's crab window. The SDL2 sim ignores this extra key.
            "agent": _session_agent(msg.get("session_id", "")),
            **{
                key: (value if isinstance(value, str) else "")[:_PERMISSION_FIELD_MAX[key]]
                for key, value in fields.items()
            },
        }
        self._enqueue_to_sims(request)
        logger.info("Permission request %s opened", request_id[:8])

        hook_gone = asyncio.ensure_future(reply.disconnected.wait())
        decision = "none"
        try:
            done, _ = await asyncio.wait(
                {future, hook_gone},
                timeout=PERMISSION_DAEMON_WAIT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if future in done:
                decision = future.result()
            elif hook_gone in done:
                # The hook process went away: the product moved on (answered in its
                # own prompt, or gave up), so the block is over, outcome unknown.
                self._resolve_permission_block(msg, "gone")
            if decision in PERMISSION_DECISIONS:
                self._resolve_permission_block(msg, decision)
        finally:
            hook_gone.cancel()
            # No-op when a decision already closed the request; otherwise the
            # hook hung up, we timed out or were cancelled: close it as "none".
            self._finish_permission(request_id, "none")
        # Always refresh the display: a resolved block just changed the state.
        await self._broadcast_display_state_if_changed()
        self._persist_sessions()
        await reply.send({"decision": decision})

    def _resolve_permission_block(self, msg: dict, outcome: str) -> None:
        """Take a session out of the permission alert once the block is resolved.

        allow -> working (the tool runs); deny/gone -> thinking (the model carries
        on, same state an answered AskUserQuestion returns to). A timeout leaves
        the alert (the product's own prompt may still be open). Only acts while the
        session is still in THAT permission block: newer activity (a question, end
        of turn) wins, and an AskUserQuestion wait is never a permission."""
        session_id = msg.get("session_id", "")
        tool = msg.get("tool_name", "")
        s = self._session_states.get(session_id)
        if (s is None or tool == ASK_USER_QUESTION_TOOL or s.get("state") != "waiting"
                or s.get("awaiting_prompt") or s.get("tool_name") != tool
                or "permission_since_monotonic" not in s):
            return
        s["state"] = "working" if outcome == "allow" else "thinking"
        s.pop("permission_since_monotonic", None)
        s["last_event"] = time.time()
        s["last_event_monotonic"] = time.monotonic()

    def _finish_permission(self, request_id: str, decision: str) -> bool:
        """Close a pending request with `decision`. First close wins; returns
        False when it was already closed. A "none" outcome also tells the desk
        window to take its bubble down."""
        record = self._pending_permissions.pop(request_id, None)
        if record is None:
            return False
        if not record["future"].done():
            record["future"].set_result(decision)
        if decision == "none":
            self._enqueue_to_sims({"event": "permission_clear", "id": request_id})
        logger.info("Permission request %s closed: %s", request_id[:8], decision)
        return True

    def _cancel_session_permissions(self, session_id: str) -> None:
        for request_id, record in list(self._pending_permissions.items()):
            if record["session_id"] == session_id:
                self._finish_permission(request_id, "none")

    def _cancel_all_permissions(self) -> None:
        for request_id in list(self._pending_permissions):
            self._finish_permission(request_id, "none")

    def handle_sim_event(self, event: dict) -> None:
        """Inbound event from a simulator connection. Only a permission decision
        matters here; it counts only when its id is still pending AND its nonce
        matches, so a stale or forged answer resolves nothing. Nothing from the
        event is logged beyond the fact that it was rejected."""
        if not isinstance(event, dict) or event.get("event") != "permission_decision":
            return
        request_id = event.get("id")
        nonce = event.get("nonce")
        decision = event.get("decision")
        record = self._pending_permissions.get(request_id) if isinstance(request_id, str) else None
        if (
            record is None
            or not isinstance(nonce, str)
            or not hmac.compare_digest(nonce.encode("utf-8"), record["nonce"].encode("utf-8"))
            or not isinstance(decision, str)
            or decision not in PERMISSION_DECISIONS
        ):
            logger.warning("Ignored a permission decision that matches no pending request")
            return
        self._finish_permission(request_id, decision)

    def _wire_sim_events(self, client) -> None:
        """Make a simulator client deliver its events to handle_sim_event, after
        any callback it already has (the menu bar window-hidden handler)."""
        if not hasattr(client, "_on_event_cb") or getattr(client, "_permission_wired", False):
            return
        previous = client._on_event_cb

        def deliver(event: dict) -> None:
            if previous is not None:
                try:
                    previous(event)
                except Exception:
                    logger.exception("Simulator event handler failed")
            self.handle_sim_event(event)

        client._on_event_cb = deliver
        client._permission_wired = True

    def _compute_display_state(self) -> dict:
        """Derive the display state from all active session states."""
        if not self._session_states:
            return {"status": "sleeping"}

        anims = []
        ids = []
        agents = []

        # Count subagents across ALL sessions, not just visible ones
        total_subagents = sum(
            len(s.get("subagents", set())) for s in self._session_states.values()
        )

        usage_low = self._usage_is_low()

        for session_id, display_id in self._session_order[:4]:
            state = self._session_states.get(session_id)
            if state is None:
                continue
            anims.append(
                _state_to_anim(state, bool(state.get("subagents")), usage_low)
            )
            ids.append(display_id)
            # Parallel to anims/ids: which product this slot belongs to, so the
            # desktop pet can pick a per-product crab and group/count by product.
            agents.append(_session_agent(session_id))

        if not anims:
            return {"status": "sleeping"}

        # Per-product aggregation (Phase 2 xN): one entry per product over ALL
        # sessions, not just the 4 visible slots, so the count is the true total.
        # The grouped view replaces the 4-slot cap, so there is no overflow here.
        all_agents = []
        all_anims = []
        all_bgs = []
        all_exhausted = []
        for session_id, _ in self._session_order:
            state = self._session_states.get(session_id)
            if state is None:
                continue
            all_agents.append(_session_agent(session_id))
            all_bgs.append(len(state.get("subagents", ())))
            all_exhausted.append(state["state"] == "out_of_credits")
            all_anims.append(
                _state_to_anim(state, bool(state.get("subagents")), usage_low)
            )
        products = _aggregate_products(all_agents, all_anims, all_bgs, all_exhausted)

        # Rich session detail is for the local desktop pet panel only. The
        # transport adapter strips it before sending to hardware.
        sessions = []
        for session_id, _ in self._session_order:
            state = self._session_states.get(session_id)
            if state is None:
                continue
            sessions.append({
                "agent": _session_agent(session_id),
                "project": state.get("project", ""),
                "state": state.get("state", "idle"),
                "tool": state.get("tool_name", ""),
                "subagents": len(state.get("subagents", ())),
            })

        result = {
            "anims": anims,
            "ids": ids,
            "agents": agents,
            "products": products,
            "sessions": sessions,
            "subagents": total_subagents,
        }
        if len(self._session_order) > 4:
            result["overflow"] = len(self._session_order) - 4
        return result

    def _usage_is_low(self) -> bool:
        """True when the 5h or weekly usage has reached LOW_BATTERY_USAGE_PCT."""
        usage = self._latest_usage or {}
        return any(
            isinstance(pct, (int, float)) and pct >= LOW_BATTERY_USAGE_PCT
            for pct in (usage.get("session_pct"), usage.get("weekly_pct"))
        )

    async def _send_session_oneshot(self, session_id: str, anim: str) -> bool:
        """Send a set_sessions with session_id's slot showing a oneshot `anim` to
        every connected v2+ transport. v1 transports have no per-session slots and
        are skipped, as are transports too old to know `anim` (a v2 firmware
        would drop the slot). Returns False when the session has no visible
        slot or no transport got the oneshot."""
        state = self._compute_display_state()
        if "anims" not in state:
            return False
        did = next((d for sid, d in self._session_order if sid == session_id), None)
        if did is None or did not in state["ids"]:
            return False
        state["anims"][state["ids"].index(did)] = anim
        sent = False
        for name, transport in self._transports.items():
            if not transport.is_connected:
                continue
            version = self._transport_versions.get(name, 1)
            if version < 2:
                continue
            if version < MIN_PROTOCOL_FOR_PHASE1_ANIMS and anim in PHASE1_ANIM_FALLBACKS:
                continue
            logger.info("Display oneshot: %s on session %s", anim, session_id[:12])
            await transport.write_notification(self._set_sessions_payload_for(name, state))
            sent = True
        return sent

    def _set_sessions_payload_for(self, name: str, state: dict) -> str:
        """set_sessions payload for a v2+ transport, with any animation name its
        protocol version does not know swapped for a fallback.

        The desktop pet (the "sim" transport) consumes the per-product fields
        (agents/products) added in Phases 1-2; the ESP32 firmware does NOT read
        them (it uses anims/ids positionally) and its GATT characteristic rejects
        a write larger than one ATT payload (MTU-3). Those fields nearly doubled
        the JSON and pushed BLE writes past the MTU, so strip them for every
        transport except the pet.

        Pet-only animation names (DESKTOP_PET_ANIM_FALLBACKS) are swapped for
        every transport not flagged `desktop_pet`, including an SDL2 "sim".
        """
        version = self._transport_versions.get(name, 1)
        downgraded = downgrade_display_state(state, version)
        if not getattr(self._transports.get(name), "desktop_pet", False):
            downgraded = _map_anims(downgraded, DESKTOP_PET_ANIM_FALLBACKS)
        if name != "sim":
            downgraded = {
                k: v for k, v in downgraded.items()
                if k not in ("agents", "products", "sessions")
            }
        elif not getattr(self._transports.get(name), "desktop_pet", False):
            # The SDL simulator shares product summaries but does not need the
            # richer list shown in the Electron activity panel.
            downgraded.pop("sessions", None)
        return display_state_to_ble_payload(downgraded)

    def _enter_state(
        self, session_id: str, state: str, tool_name: str, now: float, *, create: bool,
    ) -> None:
        """Set a session's state/tool_name/last_event. When create is False and the
        session does not exist, do nothing (avoids resurrecting an ended session)."""
        s = self._session_states.get(session_id)
        if s is None:
            if not create:
                return
            s = {"last_event": now}
            self._session_states[session_id] = s
        s["state"] = state
        s["tool_name"] = tool_name
        s["last_event"] = now
        # Every "waiting" entered here is a blocked one (permission/question);
        # only Stop/idle_prompt mark the calm end-of-turn wait.
        s.pop("awaiting_prompt", None)
        s.pop("permission_since_monotonic", None)

    def _update_session_state(
        self, event: str, hook: str, session_id: str,
        agent_id: str = "", tool_name: str = "", pid: Optional[int] = None,
        exhausted: bool = False,
    ) -> bool:
        """Update per-session state based on a received event.

        Returns True if session state or subagents changed structurally
        (not just last_event), indicating the change should be persisted.
        """
        if not session_id:
            return False
        now = time.time()
        now_mono = time.monotonic()
        prev = self._session_states.get(session_id)
        prev_state = prev["state"] if prev else None
        prev_awaiting = prev.get("awaiting_prompt", False) if prev else False
        prev_subagents = prev.get("subagents", set()).copy() if prev else None

        if event == "session_start":
            self._session_states[session_id] = {"state": "registered", "last_event": now}
        elif event in SUBAGENT_TOOL_EVENTS and agent_id and tool_name != ASK_USER_QUESTION_TOOL:
            # A subagent's own tool call (Claude Code reports it under the PARENT
            # session_id, tagged with the subagent's agent_id). It is background
            # work, not the main agent's: leave state/tool_name alone so the main
            # crab does not mimic the subagent's Bash/Edit, and let the per-product
            # `bg` count (len(subagents)) drive the pet's 'grooving'. It still
            # proves the session is alive, so refresh last_event (the monotonic
            # stamp below), and never resurrect an ended session.
            cur_s = self._session_states.get(session_id)
            if cur_s is not None:
                cur_s["last_event"] = now
        elif event == "tool_use":
            # AskUserQuestion blocks on a human choice — surface it as a distinct
            # "waiting" state (alert animation), not as ordinary work. PreToolUse is a
            # session's first signal in some flows, so it may create the session.
            new_state = "waiting" if tool_name == ASK_USER_QUESTION_TOOL else "working"
            self._enter_state(session_id, new_state, tool_name, now, create=True)
        elif event == "tool_done":
            # PostToolUse (registered scoped to AskUserQuestion): the user answered,
            # so clear the waiting alert and let Claude resume thinking. Never creates
            # a session — a PostToolUse with no prior PreToolUse is ignored.
            cur_s = self._session_states.get(session_id)
            if cur_s is not None:
                if tool_name == ASK_USER_QUESTION_TOOL and cur_s["state"] == "waiting":
                    cur_s["state"] = "thinking"
                cur_s["last_event"] = now
        elif event == "permission":
            # PermissionRequest: Claude is blocked waiting for the human to approve a
            # tool. Same "needs you" semantics as AskUserQuestion → waiting/alert. No
            # "granted" hook exists, so this clears on the next tool_use/Stop/prompt.
            # PreToolUse always precedes a real permission prompt, so never create a
            # missing session — a late event must not resurrect an ended one.
            self._enter_state(session_id, "waiting", tool_name, now, create=False)
            if session_id in self._session_states:
                self._session_states[session_id]["permission_since_monotonic"] = now_mono
        elif event == "tool_failed":
            # PostToolUseFailure: a tool genuinely errored (not a non-zero shell exit).
            # A transient "that didn't work" snag → confused, lighter than the API-error
            # 'error' state. No notification card; never resurrects an ended session.
            self._enter_state(session_id, "confused", tool_name, now, create=False)
        elif event == "compact":
            if session_id in self._session_states:
                self._session_states[session_id]["last_event"] = now
        elif event == "add":
            self._session_states.setdefault(session_id, {"state": "idle", "last_event": now})
            if hook == "Stop":
                # End of turn: the crab plays a brief happy oneshot (see
                # end_of_turn below), then rests in "waiting" (awaiting_prompt, so
                # the calm "waiting_reply" crab, not the urgent alert) so the user
                # sees it is waiting for their next prompt. This is the only "your
                # turn" signal Kiro/Codex have (no idle_prompt Notification), so it
                # must drive this state uniformly. UserPromptSubmit clears it.
                # Exception: if subagents are still running, the turn's work is not
                # really done — stay out of waiting so _compute_display_state can
                # show "conducting" instead of a false "needs you" alert.
                if self._session_states[session_id].get("subagents"):
                    self._session_states[session_id]["state"] = "idle"
                else:
                    self._session_states[session_id]["state"] = "waiting"
                    self._session_states[session_id]["awaiting_prompt"] = True
            elif hook == "Notification":
                # idle_prompt ("waiting for your input"): same end-of-turn wait as
                # Stop (waiting_reply, not the urgent alert). Drop the last tool so a
                # stale web tool can't turn a later state into "hat_mishap".
                self._session_states[session_id]["state"] = "waiting"
                self._session_states[session_id]["awaiting_prompt"] = True
                self._session_states[session_id]["tool_name"] = ""
            elif hook == "StopFailure":
                self._session_states[session_id]["state"] = (
                    "out_of_credits" if exhausted else "error"
                )
            self._session_states[session_id]["last_event"] = now
        elif event == "dismiss":
            if hook == "SessionEnd":
                self._session_states.pop(session_id, None)
                self._session_order = [(sid, did) for sid, did in self._session_order if sid != session_id]
            elif hook == "UserPromptSubmit":
                self._session_states.setdefault(session_id, {"state": "thinking", "last_event": now})
                self._session_states[session_id]["state"] = "thinking"
                self._session_states[session_id]["last_event"] = now
            else:
                if session_id in self._session_states:
                    self._session_states[session_id]["last_event"] = now
        elif event == "subagent_start":
            if not agent_id:
                return False
            self._session_states.setdefault(session_id, {"state": "working", "last_event": now})
            self._session_states[session_id].setdefault("subagents", set())
            self._session_states[session_id]["subagents"].add(agent_id)
            self._session_states[session_id]["last_event"] = now
        elif event == "subagent_stop":
            if session_id in self._session_states:
                subagents = self._session_states[session_id].get("subagents")
                if subagents is not None:
                    subagents.discard(agent_id)
                self._session_states[session_id]["last_event"] = now

        # Track session order — append on first appearance
        cur = self._session_states.get(session_id)
        if cur is not None and session_id not in [sid for sid, _ in self._session_order]:
            self._session_order.append((session_id, self._next_display_id))
            self._next_display_id += 1

        # Stamp PID + monotonic on every event (only if session still exists —
        # SessionEnd may have just removed it).
        if cur is not None:
            if pid is not None:
                cur["pid"] = pid
            cur["last_event_monotonic"] = now_mono

        if cur is None:
            return prev is not None  # session was removed
        return (
            cur["state"] != prev_state
            or cur.get("awaiting_prompt", False) != prev_awaiting
            or cur.get("subagents", set()) != (prev_subagents or set())
        )

    def _evict_stale_sessions(self) -> None:
        # Active subagents refresh last_event via PreToolUse on the parent session.
        # If last_event_monotonic is stale, subagents are dead too — safe to evict.
        # Uses monotonic time so macOS sleep doesn't trigger mass-eviction on wake.
        now_mono = time.monotonic()
        stale = []
        for sid, s in self._session_states.items():
            # 'waiting' sessions legitimately emit no events, so they are exempt
            # from time-based eviction: a blocked one (permission/AskUserQuestion,
            # no awaiting_prompt) must keep its alert while the user is away, and a
            # PID-backed end-of-turn rest is covered by the liveness checker.
            # The one exception is an end-of-turn rest (awaiting_prompt) with no
            # PID and no running subagents: nothing else would ever remove it
            # (Antigravity and other PID-less agents send no SessionEnd), so it
            # expires with the NORMAL timeout below (the user may be thinking, so
            # not the short no-PID one).
            if s.get("state") == "waiting":
                if not (s.get("awaiting_prompt") and s.get("pid") is None
                        and not s.get("subagents")):
                    continue
                if now_mono - s.get("last_event_monotonic", now_mono) > self._session_staleness_timeout:
                    stale.append(sid)
                continue
            # Adaptive timeout: PID-backed sessions are already covered by the
            # liveness checker (evicted the instant the process dies), so they
            # keep the long timeout. Sessions with no PID (failed detection,
            # e.g. no claude.exe ancestor on Windows) have no such safety net,
            # so they expire much sooner.
            # Sessions Kiro's log reported (no PID ever) sit idle at rest without
            # events, so they keep the normal timeout while in a resting state.
            has_pid = s.get("pid") is not None
            log_resting = s.get("log_seen") and s.get("state") in LOG_RESTING_STATES
            timeout = (self._session_staleness_timeout if has_pid or log_resting
                       else NO_PID_STALENESS_TIMEOUT)
            idle = now_mono - s.get("last_event_monotonic", now_mono)
            if idle > timeout:
                stale.append(sid)
        for sid in stale:
            logger.info("Evicting stale session: %s", sid[:12])
            del self._session_states[sid]
            self._active_notifications.pop(sid, None)
        if stale:
            self._session_order = [(sid, did) for sid, did in self._session_order if sid not in stale]
            self._persist_sessions()

    def _persist_sessions(self) -> None:
        save_sessions(
            self._session_states,
            self._sessions_path,
            order=self._session_order,
            next_id=self._next_display_id,
        )

    async def _broadcast_display_state_if_changed(self, force: bool = False) -> None:
        """Broadcast display state to all connected transports if changed (or
        unconditionally with force=True)."""
        new_state = self._compute_display_state()
        if new_state == self._last_display_state and not force:
            return
        self._last_display_state = new_state
        if "anims" in new_state:
            logger.info("Display: anims=%s subagents=%d%s",
                        new_state["anims"], new_state.get("subagents", 0),
                        f" overflow={new_state['overflow']}" if "overflow" in new_state else "")
        else:
            logger.info("Display: %s", new_state.get("status", "?"))
        for name, transport in self._transports.items():
            if transport.is_connected:
                version = self._transport_versions.get(name, 1)
                if version >= 2:
                    payload = self._set_sessions_payload_for(name, new_state)
                else:
                    payload = display_state_to_v1_payload(new_state)
                await transport.write_notification(payload)

    async def _broadcast_usage(self) -> None:
        """Read the usage cache and push a set_usage payload to all connected
        transports. Only sends when the values change to avoid redundant writes."""
        usage = read_usage_from_cache(USAGE_CACHE_PATH)
        if usage is None:
            return
        self._latest_usage = usage
        payload = usage_to_ble_payload(
            usage.get("session_pct"),
            usage.get("weekly_pct"),
            usage.get("reset_seconds"),
        )
        # Skip identical resend (reset_seconds shifts slowly so compare on a
        # coarse key: pcts + minute-rounded reset).
        session_pct = usage.get("session_pct")
        weekly_pct = usage.get("weekly_pct")
        reset_s = usage.get("reset_seconds")
        reset_min = reset_s // 60 if isinstance(reset_s, int) else None
        key = (session_pct, weekly_pct, reset_min)
        if key == self._last_usage_key:
            return
        self._last_usage_key = key

        for name, transport in self._transports.items():
            if transport.is_connected:
                try:
                    await transport.write_notification(payload)
                except Exception:
                    logger.exception("Failed to send usage to '%s'", name)

        # Usage crossing LOW_BATTERY_USAGE_PCT flips idle crabs to/from
        # "low_battery"; no-op when the display state did not change.
        await self._broadcast_display_state_if_changed()

    async def _usage_checker(self) -> None:
        """Async task: periodically poll the usage cache and broadcast it."""
        while self._running:
            await asyncio.sleep(USAGE_POLL_INTERVAL_SECS)
            await self._broadcast_usage()

    async def _refresh_project_usage(self) -> None:
        """Export every pass, then push changed Claude usage to desktop pets."""
        self._project_usage_readers["claude"] = self._project_usage_reader
        for name, reader in self._project_usage_readers.items():
            try:
                await asyncio.to_thread(reader.refresh)
                if name == "claude" and isinstance(reader, ClaudeUsageReader):
                    reader.status = "ok" if reader._root.is_dir() else "absent"
            except Exception:
                reader.status = "error"
                logger.exception("Project usage refresh failed for %s", name)
        now = datetime.now().astimezone()
        self._project_usage_document = build_document(
            self._project_usage_readers, now, self._project_usage_document)
        await asyncio.to_thread(write_json_atomic, self._project_usage_path, self._project_usage_document)
        try:
            reader = self._project_usage_reader
            if getattr(reader, "status", "ok") == "error":
                return
            payload = project_usage_to_payload(reader.snapshot(now))
        except Exception:
            logger.exception("Project usage refresh failed")
            return
        if payload == self._project_usage_payload:
            return
        self._project_usage_payload = payload
        for name, transport in self._transports.items():
            if getattr(transport, "desktop_pet", False) and transport.is_connected:
                try:
                    await transport.write_notification(payload)
                except Exception:
                    logger.exception("Failed to send project usage to '%s'", name)

    async def _project_usage_checker(self) -> None:
        while self._running:
            await self._refresh_project_usage()
            await asyncio.sleep(PROJECT_USAGE_POLL_INTERVAL_SECS)

    async def _staleness_checker(self) -> None:
        while self._running:
            await asyncio.sleep(30)
            self._evict_stale_sessions()
            await self._broadcast_display_state_if_changed()

    def _check_liveness(self) -> list[str]:
        """Synchronous half of the liveness check — separated for testability.

        Returns the list of evicted session_ids.
        """
        dead = []
        for sid, state in self._session_states.items():
            pid = state.get("pid")
            if pid is None:
                continue
            if not pid_alive(pid):
                dead.append(sid)
        for sid in dead:
            logger.info(
                "Liveness: evicting session %s (PID %d gone)",
                sid[:12], self._session_states[sid].get("pid"),
            )
            del self._session_states[sid]
            self._session_order = [(s, d) for s, d in self._session_order if s != sid]
            self._active_notifications.pop(sid, None)
        if dead:
            self._persist_sessions()
        return dead

    async def _liveness_checker(self) -> None:
        """Async task: every PID_LIVENESS_INTERVAL_SECS, evict sessions whose
        Claude Code PID is gone."""
        while self._running:
            await asyncio.sleep(PID_LIVENESS_INTERVAL_SECS)
            evicted = self._check_liveness()
            if evicted:
                await self._broadcast_display_state_if_changed()

    async def _probe_ble_liveness(self) -> None:
        """One liveness sweep: round-trip probe every connected, probe-capable
        transport. A failed probe drops the client inside ping(), which flips
        is_connected to False so _transport_sender re-scans and reconnects. TCP
        transports (the simulator) detect disconnects natively and expose no
        ping(), so they are skipped via duck typing."""
        for name, transport in list(self._transports.items()):
            # A prior probe's await may have let remove_transport() run; don't
            # probe a transport that was disabled mid-sweep.
            if name not in self._transports:
                continue
            probe = getattr(transport, "ping", None)
            if probe is None or not transport.is_connected:
                continue
            try:
                alive = await probe()
                if not alive:
                    logger.warning(
                        "Transport '%s' liveness probe failed; sender will reconnect",
                        name,
                    )
            except Exception:
                logger.exception("Transport '%s' liveness probe raised", name)

    async def _ble_liveness_checker(self) -> None:
        """Async task: periodically probe BLE links so dead connections that
        CoreBluetooth never reported are detected and reconnected."""
        while self._running:
            await asyncio.sleep(BLE_LIVENESS_INTERVAL_SECS)
            await self._probe_ble_liveness()

    def set_session_timeout(self, seconds: int) -> None:
        self._session_staleness_timeout = float(seconds)
        logger.info("Session staleness timeout set to %ds", seconds)

    def _on_transport_connect(self, name: str) -> None:
        """Called by a transport client on successful connection."""
        logger.info("Transport '%s' connected", name)
        # Simulator always supports latest protocol; BLE defaults to v1
        if name.startswith("sim"):
            self._transport_versions[name] = SIM_PROTOCOL_VERSION
        if self._observer:
            self._observer.on_connection_change(True, name)

    def _on_transport_disconnect(self, name: str) -> None:
        """Called by a transport client on disconnect."""
        logger.warning("Transport '%s' disconnected", name)
        if self._observer:
            self._observer.on_connection_change(False, name)

    async def _sync_time_for(self, transport) -> None:
        """Send current host time and timezone to a transport."""
        epoch = int(time.time())
        # Build POSIX TZ string from local UTC offset
        # POSIX TZ signs are inverted: UTC+3 means 3 hours *west* of Greenwich
        utc_offset = time.localtime().tm_gmtoff  # seconds east of UTC
        sign = "-" if utc_offset >= 0 else "+"  # inverted for POSIX
        abs_offset = abs(utc_offset)
        hours, remainder = divmod(abs_offset, 3600)
        minutes = remainder // 60
        tz = f"UTC{sign}{hours}" if minutes == 0 else f"UTC{sign}{hours}:{minutes:02d}"
        payload = json.dumps({"action": "set_time", "epoch": epoch, "tz": tz})
        await transport.write_notification(payload)
        logger.info("Synced time: epoch %d, tz %s", epoch, tz)

    async def _post_connect_sync(self, transport, name: str) -> None:
        """Run time sync, version read, and replay after a (re)connection."""
        await self._sync_time_for(transport)
        if hasattr(transport, 'read_version') and callable(getattr(transport, 'read_version', None)):
            try:
                version = await transport.read_version()
                if isinstance(version, int) and version >= 1:
                    self._transport_versions[name] = version
                    logger.info("Transport '%s': protocol version %d", name, version)
            except Exception:
                self._transport_versions[name] = 1
                logger.warning("Transport '%s': version read failed, defaulting to v1", name)
        await self._replay_active_for(transport, name)
        # Push current usage right away so the new connection shows it without
        # waiting for the next poll tick. Reset the dedup key so it always sends.
        self._last_usage_key = None
        await self._broadcast_usage()
        if self._project_usage_payload and getattr(transport, "desktop_pet", False):
            await transport.write_notification(self._project_usage_payload)

    async def _replay_active_for(self, transport, name: str = "") -> None:
        """Replay all active notifications to a transport after reconnect."""
        logger.info("Replaying %d active notifications", len(self._active_notifications))
        for msg in list(self._active_notifications.values()):
            try:
                payload = daemon_message_to_ble_payload(msg)
            except ValueError:
                continue
            if payload is None:
                continue
            await transport.write_notification(payload)
            await asyncio.sleep(0.05)

        # Send current display state
        state = self._compute_display_state()
        self._last_display_state = state
        version = self._transport_versions.get(name, 1)
        if version >= 2:
            status_payload = self._set_sessions_payload_for(name, state)
        else:
            status_payload = display_state_to_v1_payload(state)
        await transport.write_notification(status_payload)

    async def _transport_sender(self, name: str) -> None:
        """Keep a named transport's sender running.

        The sender is the only thing that connects a transport on its own and
        drains its queue, and its task is not awaited by anyone until shutdown,
        so an exception that escaped it used to vanish without a trace and
        leave the transport dead until the user clicked Reconnect (which calls
        ensure_connected() directly). Log every crash with its traceback and
        restart the sender after a growing delay. Cancellation still ends it.
        """
        crashes = 0
        while self._running:
            started = time.monotonic()
            try:
                await self._run_transport_sender(name)
                return
            except Exception:
                if time.monotonic() - started >= SENDER_STABLE_SECS:
                    crashes = 0
                crashes += 1
                delay = min(
                    SENDER_RESTART_MAX_SECS,
                    SENDER_RESTART_BASE_SECS * 2 ** min(crashes - 1, 10),
                )
                logger.exception(
                    "Transport '%s' sender crashed (%d in a row); restarting in %gs",
                    name, crashes, delay,
                )
                await asyncio.sleep(delay)

    async def _run_transport_sender(self, name: str) -> None:
        """Process pending messages and send them over a named transport."""
        transport = self._transports[name]
        queue = self._transport_queues[name]
        # Initial connection — retries until connected
        await transport.ensure_connected()
        if transport.is_connected:
            await self._post_connect_sync(transport, name)
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    queue.get(), timeout=SENDER_IDLE_POLL_SECS
                )
            except asyncio.TimeoutError:
                # Proactively reconnect if transport dropped
                if not transport.is_connected:
                    await transport.ensure_connected()
                    if transport.is_connected:
                        await self._post_connect_sync(transport, name)
                continue
            if (
                msg.get("event") in ("permission_request", "permission_clear")
                and not name.startswith("sim")
            ):
                continue  # the bubble exists on the simulator only
            try:
                payload = daemon_message_to_ble_payload(msg)
            except ValueError:
                logger.error("[%s] Skipping unknown event: %s", name, msg.get("event"))
                continue
            if payload is None:
                continue

            was_connected = transport.is_connected
            await transport.ensure_connected()
            if not was_connected and transport.is_connected:
                await self._post_connect_sync(transport, name)

            success = await transport.write_notification(payload)

            if not success:
                await transport.ensure_connected()
                if transport.is_connected:
                    await self._post_connect_sync(transport, name)

    def _write_pid(self) -> None:
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        if PID_PATH.exists():
            PID_PATH.unlink()

    async def _shutdown(self) -> None:
        logger.info("Shutting down...")
        self._running = False
        self._cancel_all_permissions()
        try:
            await self._cleanup()
        finally:
            # Wake run() only once cleanup is done (or has failed). Waking it
            # first lets the owner stop the event loop mid-cleanup, which
            # abandons the transport disconnect, socket stop and PID removal.
            self._shutdown_event.set()

    async def _cleanup(self) -> None:
        if hasattr(self, '_staleness_task'):
            self._staleness_task.cancel()
            try:
                await self._staleness_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_liveness_task'):
            self._liveness_task.cancel()
            try:
                await self._liveness_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_usage_task'):
            self._usage_task.cancel()
            try:
                await self._usage_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_project_usage_task'):
            self._project_usage_task.cancel()
            try:
                await self._project_usage_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_ble_liveness_task'):
            self._ble_liveness_task.cancel()
            try:
                await self._ble_liveness_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, '_kiro_log_task'):
            self._kiro_log_task.cancel()
            try:
                await self._kiro_log_task
            except asyncio.CancelledError:
                pass

        for task in self._sender_tasks.values():
            task.cancel()
        for task in self._sender_tasks.values():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._sender_tasks.clear()

        clear_payload = daemon_message_to_ble_payload({"event": "clear"})
        for transport in self._transports.values():
            if transport.is_connected:
                await transport.write_notification(clear_payload)
            await transport.disconnect()
        await self._socket.stop()
        self._remove_pid()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    async def add_transport(self, name: str, client: TransportClient) -> None:
        """Add a transport dynamically and start its sender task."""
        # A sender already running under this name would keep driving the
        # transport alongside the new one (two scan/connect loops against a
        # device that accepts a single connection). Stop it first.
        previous = self._sender_tasks.pop(name, None)
        if previous is not None and not previous.done():
            previous.cancel()
            try:
                await previous
            except asyncio.CancelledError:
                pass
        client._on_connect_cb = lambda: self._on_transport_connect(name)
        client._on_disconnect_cb = lambda: self._on_transport_disconnect(name)
        self._wire_sim_events(client)
        self._transports[name] = client
        self._transport_queues[name] = asyncio.Queue()
        self._sender_tasks[name] = asyncio.create_task(self._transport_sender(name))

    async def remove_transport(self, name: str) -> None:
        """Stop sender task, disconnect client, and remove transport."""
        if name in self._sender_tasks:
            self._sender_tasks[name].cancel()
            try:
                await self._sender_tasks[name]
            except asyncio.CancelledError:
                pass
            del self._sender_tasks[name]
        if name in self._transports:
            client = self._transports[name]
            if client.is_connected:
                await client.disconnect()
            del self._transports[name]
        self._transport_queues.pop(name, None)
        self._on_transport_disconnect(name)

    async def read_config(self) -> dict:
        """Read config from the first connected transport."""
        for transport in self._transports.values():
            if transport.is_connected:
                return await transport.read_config()
        return {}

    async def write_config(self, payload: str) -> bool:
        """Write config to all connected transports."""
        success = False
        for transport in self._transports.values():
            if transport.is_connected:
                if await transport.write_config(payload):
                    success = True
        return success

    async def reconnect(self) -> None:
        """Force a full reconnect + post-connect sync on all transports."""
        for name, transport in self._transports.items():
            try:
                await transport.disconnect()
            except Exception:
                logger.warning("Transport '%s' disconnect failed during reconnect", name)
            try:
                await transport.ensure_connected()
                if transport.is_connected:
                    await self._post_connect_sync(transport, name)
            except Exception:
                logger.exception("Transport '%s' reconnect failed", name)

    def _install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Route SIGTERM/SIGINT to _shutdown() — separated for testability."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self._shutdown()))
            except NotImplementedError:
                # Windows' ProactorEventLoop has no add_signal_handler. The
                # signal module runs the handler on the main thread outside the
                # loop, so hop back onto it before touching daemon state.
                signal.signal(
                    sig,
                    lambda _signum, _frame: loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._shutdown())
                    ),
                )

    def _run_startup(self) -> None:
        """Run the startup callable; a failure is logged and never stops the daemon."""
        if self._startup is None:
            return
        try:
            self._startup()
        except Exception:
            logger.exception("Daemon startup task failed")

    async def run(self) -> None:
        """Main daemon loop."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

        self._lock_fd = _acquire_lock(takeover=not self._headless)
        self._run_startup()
        self._write_pid()

        if self._headless:
            self._install_signal_handlers(asyncio.get_running_loop())

        await self._socket.start()

        for name in self._transports:
            # add_transport() may have landed while the socket server was
            # starting (the menu bar schedules it right after run()); that
            # transport already has a sender, and a second one would run a
            # concurrent connect loop against the same device.
            existing = self._sender_tasks.get(name)
            if existing is not None and not existing.done():
                continue
            # Each sender handles its own connect via ensure_connected()
            self._sender_tasks[name] = asyncio.create_task(self._transport_sender(name))

        self._staleness_task = asyncio.create_task(self._staleness_checker())
        self._liveness_task = asyncio.create_task(self._liveness_checker())
        self._ble_liveness_task = asyncio.create_task(self._ble_liveness_checker())
        self._usage_task = asyncio.create_task(self._usage_checker())
        self._project_usage_task = asyncio.create_task(self._project_usage_checker())
        self._kiro_log_task = asyncio.create_task(run_kiro_log_watcher(self._handle_message))

        await self._shutdown_event.wait()
        logger.info("Daemon run() finished")


def _build_daemon(argv=None) -> "ClawdDaemon":
    """Build a headless daemon from CLI flags and ~/.clawd-tank/preferences.json.

    Explicit --sim/--sim-only/--sim-port keep today's transport logic and win
    over ble_enabled/sim_enabled. sim_desk_mode marks the simulator transport
    as the desktop pet. sim_window_visible/sim_always_on_top are tray-only.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Clawd Tank daemon")
    parser.add_argument("--sim", action="store_true",
                        help="Enable simulator transport (BLE + TCP)")
    parser.add_argument("--sim-only", action="store_true",
                        help="Simulator only (no BLE)")
    parser.add_argument("--sim-port", type=int, default=SIM_DEFAULT_PORT,
                        help=f"Simulator TCP port (default: {SIM_DEFAULT_PORT})")
    parser.add_argument("--no-install-hooks", action="store_true",
                        help="Do not install/update Claude Code hooks on start")
    args = parser.parse_args(argv)

    # Lazy: stdlib-only modules of the tray package (its __init__ is empty).
    from clawd_tank_menubar import hooks
    from clawd_tank_menubar.preferences import load_preferences
    prefs = load_preferences()

    if args.sim or args.sim_only or args.sim_port != SIM_DEFAULT_PORT:
        sim_port, sim_only, ble_enabled = args.sim_port, args.sim_only, True
    else:
        sim_port = SIM_DEFAULT_PORT if prefs.get("sim_enabled", True) else 0
        sim_only, ble_enabled = False, bool(prefs.get("ble_enabled", True))

    return ClawdDaemon(
        sim_port=sim_port,
        sim_only=sim_only,
        ble_enabled=ble_enabled,
        sim_desktop_pet=bool(prefs.get("sim_desk_mode", False)),
        startup=None if args.no_install_hooks else hooks.ensure_hooks_current,
    )


def main():
    asyncio.run(_build_daemon().run())


if __name__ == "__main__":
    main()
