# Exploration: Tauri 2 shell + hotbar migration

## Answer first

- Adopt **Approach A: phased strangler** to Tauri 2, keeping Electron as a fallback until parity.
- Gate the shell migration behind a **throwaway Windows-first spike** (go/no-go).
- The **first change is daemon-side only** (usage data model + headless parity). It is shell-agnostic, low risk, and ships even if the spike fails.

## User intent

- A floating, always-on-top, draggable, collapsible **hotbar** (reference: github.com/montesgp/orbitbar) inside this repo, acting as the control center for the pets. Its information must be usable from each pet and from the hotbar.
- v1 content: **Claude Code token usage and cost per project**.
- Migrate the shell to **Tauri 2** with **one installer for Windows, macOS and Linux**.
- Hard constraints: keep the pets; do not break CLI/IDE hooks and the permission flow (Claude Code, Codex, Kiro, OpenCode, Antigravity); do not break BLE with the ESP32-C6.

## Current state

- **Shell**: Electron 33 (`desktop/main.js`) renders one pet window per agent, the permission card and the activity panel. It is a TCP server on `127.0.0.1:19872`; the daemon is the client.
- **Daemon**: Python asyncio; single source of truth for session state; transports BLE (`ble_client.py`, bleak) and TCP sim/pet.
- **Headless daemon**: `daemon.py:1674-1690` handles only `--sim/--sim-only/--sim-port`. It does not apply `preferences.json`, install/update hooks, or manage autostart; the trays (`windows_tray.py`, `rumps_view.py`, `controller.py`) do.
- **Hook paths**: `hooks.py:1107-1165` resolve notify/statusline commands from `sys.executable` at import. Moving the daemon to another folder changes every hook path. On macOS the notify script relies on system `python3`.
- **Usage today**: only rate-limit percentages (Claude statusline cache, Kiro, Antigravity); OpenCode/Codex usage read in Electron. **No per-project token/cost reader exists.** Claude Code jsonl exposes `cwd`, `sessionId`, `message.model`, `message.usage.{input,output,cache_creation_input,cache_read_input}_tokens`.
- **Packaging**: py2app (macOS, ad-hoc sign), PyInstaller onedir + Inno Setup (Windows, unsigned), files of `desktop/` copied by explicit list in `release.yml`. No Linux build. CI does not run tests.

## Affected areas

| Area | Change |
| --- | --- |
| `host/clawd_tank_daemon/daemon.py` | Complete headless mode; usage aggregator; new protocol action |
| `host/clawd_tank_daemon/protocol.py` | Additive hotbar/pet usage action (v1/v2/v3 unaffected) |
| `host/clawd_tank_menubar/hooks.py` | Hook path resolution independent of the shell exe |
| `host/clawd_tank_menubar/{windows_tray,rumps_view,controller}.py` | Tray parity targets; retired later |
| `desktop/*` | Port source for pet windows, permission card, panel |
| `host/clawd_tank_daemon/sim_process.py` | Lifecycle; parent-death watchdog for sidecar |
| `host/windows/*`, `host/setup.py`, `.github/workflows/release.yml` | Replaced in the packaging phase |
| `src-tauri/` (new) | Spike and Tauri shell |
| `firmware/`, `ble_client.py` | **Untouched** |

## Preservation contract (must not change)

- **TCP protocol**: all existing actions and outbound events, port 19872, v1/v2/v3 negotiation and downgrade rules. New actions are additive and never sent to transports that cannot handle them.
- **Permission flow**: `permission_request {id, nonce, ...}` → `permission_decision {id, nonce, decision}` stays byte-compatible; the shell only renders and relays.
- **Hooks**: event set, notify/statusline commands, `--uninstall-hooks`, ownership/prune rules. Hook paths stay valid across upgrades and shell swaps. Other tools' hooks are never touched.
- **BLE**: `ble_client.py`, bleak `<1.0`, GATT UUIDs, version characteristic, firmware. macOS keeps `NSBluetoothAlwaysUsageDescription` and bundle id `com.clawd-tank.menubar` (preserves the TCC grant).
- **Paths**: `~/.clawd-tank/` (preferences, sessions, notify script, endpoint.json), `~/Library/Logs/ClawdTank`, launchd label.
- **Pets**: animations, multi-slot behavior, renderer assets.
- **Branding**: "Margarita Tank", unversioned release asset names.

## Approaches

| | A. Tauri phased strangler | B. Electron + electron-builder | C. Tauri big-bang |
| --- | --- | --- | --- |
| Idea | Daemon work first, spike gate, Tauri shell behind a flag, retire Electron at parity | Hotbar as Electron window; electron-builder replaces Inno/py2app | Rewrite shell, tray, packaging, Linux at once |
| Pros | Shippable, reversible phases; meets "lighter, one ecosystem"; data model lands early | Lowest risk; proven click-through/always-on-top | Single cutover |
| Cons | Temporary dual-shell maintenance | Misses the lightweight/Tauri goal | Highest risk, no fallback, far over review budget |
| Effort | High, spread over 3-4 changes | Medium | Very high |

**Recommendation**: A. B is the explicit fallback if the spike fails. Reject C.

## Proposed change sequence

- **Change 0 (throwaway spike, not merged)**: Windows; transparent always-on-top Tauri window, Rust cursor-polling click-through, Allow/Deny card round-tripping a real nonce through the daemon. Written pass/fail criteria before starting.
- **Change 1 (this change's first scope)**: daemon Claude Code usage reader (tokens + estimated cost per project, price table, tests); additive protocol action for hotbar/pet usage; complete headless mode (preferences, hooks install/update, autostart decoupled from tray); notify/statusline path resolution independent of the shell exe.
- **Change 2**: Tauri shell — tray parity, sidecar daemon (PyInstaller onedir + parent-death watchdog), hotbar window, ported pet windows, behind a flag.
- **Change 3**: unified packaging (NSIS currentUser + `NSIS_HOOK_PREUNINSTALL` running `--uninstall-hooks`, dmg, deb/rpm/AppImage), CI matrix per OS, Linux, retire Electron/py2app/Inno.

## Risks

| Severity | Risk |
| --- | --- |
| High | Windows/Linux selective click-through: no `forward` in Tauri (#13070); Rust cursor polling required. Covered by spike. |
| High | macOS pets/permission card over fullscreen needs community `tauri-nspanel` (#11488); `focusable:false` broken (#14102); DMG transparency loss (#13415). |
| High | Hook breakage on upgrade/uninstall: paths derive from `sys.executable`; hooks pointing at deleted exes break Claude Code. |
| High | Sidecar lifecycle: onefile orphans (#11686) → onedir; watchdog needed, otherwise orphan daemon holds the BLE link. |
| High | macOS Bluetooth TCC attribution for a sidecar is unverified; a missing/misattributed grant aborts the process (SIGABRT). |
| Medium | Signing/notarization/universal builds (#9422, #11992); updater requires signing. |
| Medium | Token/cost semantics: cache-token pricing and price drift; must be labeled an estimate with sourced prices. |
| Medium | Windows bleak/winrt modules not explicitly collected in the PyInstaller spec. |
| Medium | Dual-shell maintenance during the strangler period. |
| Medium | Linux is new surface: AppIndicator tray without icon clicks, WebKitGTK transparency on Wayland, BlueZ permissions. |
| Low | Review budget: the full migration must be chained/split. |

## Open questions

1. Cost source: local price table (estimate) vs statusline value where available.
2. Per-project key: cwd basename (current pet label), git root, or Claude project dir.
3. Must the spike's go/no-go include macOS, or Windows only?
4. Is Electron retired at parity or kept for one release as fallback?
5. Spike pass/fail thresholds (idle CPU/RAM, click-through latency).
6. Does the Tauri shell own autostart, or the daemon?

## Ready for proposal

Yes, for Change 1 (daemon data model + headless parity), with the spike tracked separately.
