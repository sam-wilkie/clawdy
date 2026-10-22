## Exploration: tauri-shell-hotbar (Change 2)

### Current state
- **Electron pet** (`desktop/main.js`, 583 lines):
  - One transparent window per agent, ordered `claude, codex, kiro, opencode, antigravity, pi`, stacked bottom-right.
  - The activity panel (`openPanel`, `dashboard.html/js`) pops up on click.
  - The permission bubble lives inside each pet window. It has a queue, a 350 ms click guard, replay on `ready-for-state`, and `permission_clear`.
  - The TCP server on 127.0.0.1:19872 is in `daemon-bridge.js`. The daemon is the client (`SimClient`). The bridge answers `read_config` with `{"sleep_timeout":0}`.
  - It handles `quit`, `set_sessions`, `set_status`, `set_usage`, `permission_request` and `permission_clear`. It ignores unknown actions, including `set_project_usage`.
  - Parent-death watchdog on `CLAWDY_PARENT_PID` (JS only).
- **Usage readers are in JS and not cheaply portable to Rust.**
  - `codex-usage.js` spawns the `codex` app-server and handles the reset credit.
  - `agent-usage.js` reads Kiro through `sql.js`, runs the OpenCode CLI, and reads Claude from `~/.clawd-tank/statusline-cache.json`.
  - `antigravity-usage.js` uses `sql.js`.
- **Tray and process ownership**:
  - The Python tray owns the daemon thread and spawns Electron through `SimProcessManager._find_desktop_pet()` in `host/clawd_tank_daemon/sim_process.py`. It passes `CLAWDY_PORT` and `CLAWDY_PARENT_PID`.
  - The daemon has no parent-death watchdog.
  - Only the tray has these controls:
    - BLE and sim toggles.
    - Hook toggles for Kiro, OpenCode, Pi and Antigravity.
    - Brightness and session timeout.
    - The login item (`autostart.py`, HKCU Run value `ClawdTank`).
- **Change 1 delivered**:
  - A headless daemon (`python -m clawd_tank_daemon.daemon`) that applies prefs and hooks. It takes the lock without takeover, so it exits if the tray daemon already holds it.
  - `set_project_usage` sent to `desktop_pet` transports.
  - `CLAWD_TANK_HOOK_EXE_DIR`.
  - Gap: headless sets `desktop_pet` only through the pref `sim_desk_mode`. There is no CLI flag.
- **Spike** (`spike/tauri/`):
  - Windows click-through, CPU, RAM (at most 10% over Electron) and the nonce round trip all pass.
  - macOS is unverified under accepted risk L20 (tauri#11488 / #14102).
  - It measured ONE window only. Electron uses six, and the real shell would use one under option A.

### Affected areas
- New `shell/src-tauri/` and `shell/ui/`: Rust bridge, commands, sidecar, tray, vanilla JS/HTML/CSS. Build with `cargo tauri` and `withGlobalTauri`, so there are no node dependencies.
- `host/clawd_tank_daemon/sim_process.py`: Tauri branch in `_find_desktop_pet`.
- `host/clawd_tank_daemon/daemon.py`: `--desktop-pet` flag and a parent-PID watchdog.
- `host/clawd_tank_menubar/preferences.py`: `shell` key.
- Reuse from `desktop/renderer/`: `anim-map.js` and the SVG assets. Do not duplicate the assets; copy them in a pre-build step until Electron is retired in Change 3.

### Spike: promote vs rewrite
- **Promote**:
  - The `tauri.conf.json` window flags.
  - The `capabilities/default.json` gotcha: without `core:default`, buttons silently do nothing.
  - `tests/t3_roundtrip.py`, `t3_wrong_nonce.py` and `t4_clickthrough.py`, as integration scripts.
  - The adaptive polling loop, only as a fallback.
- **Rewrite**:
  - The TCP bridge. It uses `line.contains` parsing, handles a single connection, has no `read_config` reply, no `quit` and no reconnect. Use `serde_json` and a state struct.
  - The commands.
  - `csp: null`. Tighten it, and restrict the permission-decision command to the hotbar window.

### Change 2 contents vs deferral to Change 3
- **In Change 2**:
  - Bridge: framing, `read_config`, `quit`, link state, `set_status` fallback.
  - Product state and cells with animations.
  - Permission card with the same semantics as Electron (queue, guard, replay, clear, nonce echo).
  - `set_usage` meters.
  - `set_project_usage` list, which is the hotbar's first content.
  - Minimal sessions popover.
  - Parent watchdog in the daemon.
  - The flag.
  - Standalone sidecar mode.
  - Tray with Show/Hide, Launch at login and Quit.
- **Defer**:
  - Codex, Kiro, OpenCode and Antigravity usage readers. Port them into the Python daemon next to `claude_usage.py`. This is a separate change, "2b".
  - Codex reset credit.
  - Shake-to-dizzy, walking and going_away flourishes.
  - Per-agent taskbar icons.
  - Full tray settings parity (hook toggles, BLE, brightness, session timeout).
  - Linux.
  - Installer, onedir packaging, Electron retirement and the CI matrix (Change 3).

### Hotbar UX options (inspired by orbitbar)
Verified orbitbar behavior: a docked bar at the right edge of the primary monitor with a configurable margin. It is draggable across monitors and its position persists, with off-screen clamping. A chevron collapses it to a tab. Popovers open on the left, or the right if there is no room, and never move the bar. It is single-instance. It was manually verified on Windows only.

| Option | Pros | Cons | Effort |
|---|---|---|---|
| **A. Docked bar, one window.** Six cells with small animated pets, an xN badge, a popover for sessions/usage/permission, and a collapse chevron. The window resizes to its content. | Lightest (one webview). No click-through polling needed. Removes the 1.5% idle CPU. Reduces macOS click-through risk. | Smaller pets. Loses the free-roaming crab charm. | Medium |
| B. Keep six floating pets plus a launcher strip. | Full parity with today. | Six webviews, and RAM times 6 is unmeasured. Contradicts the "lighter shell" goal. | High |
| C. Wide transparent "stage" strip with full-size pets. | Keeps the charm. | Needs multi-rect polling. Keeps the polling CPU cost. Larger permission-card interactive region. | Medium-High |

**Recommendation: A.**
- Position: a persisted right-edge default, clamped to a monitor.
- Drag: `data-tauri-drag-region`, which needs the start-dragging capability.
- A pulsing cell signals a pending permission.
- Add a "tear-off" pet later only if requested.

### Feature flag
- Resolve in this order: env `CLAWDY_SHELL`, then `preferences.json` `shell` ("electron" default | "tauri").
- `_find_desktop_pet()` returns `[tauri_exe]` for Tauri. Locate the exe via `CLAWDY_SHELL_EXE`, next to `sys.executable`, or `shell/src-tauri/target/release`.
- It sets the same env as Electron (`CLAWDY_PORT`, `CLAWDY_PARENT_PID`). The daemon still sees a `desktop_pet` transport, so `set_project_usage` flows.
- If the Tauri exe is missing, fall back to Electron with a warning. Never leave the user without a pet.

### Two modes in one binary
The mode is chosen by whether `CLAWDY_PARENT_PID` is set.
- **Hosted (tray-spawned)**: the Electron contract. TCP server only, no sidecar, tray or autostart. This is the lowest-risk mode and ships first.
- **Standalone**: Tauri spawns the headless daemon as a sidecar, with its own tray and autostart.

### Sidecar and daemon lifecycle
| Option | Verdict |
|---|---|
| **S2 (recommended)**: Rust `std::process::Command` on the bundled PyInstaller onedir exe (dev: `host/.venv` python `-m clawd_tank_daemon.daemon --desktop-pet`). Use a Windows Job Object with KILL_ON_JOB_CLOSE, plus a Python-side `CLAWDY_PARENT_PID` watchdog on all platforms. | Handles orphans (#11686) and avoids the BLE-holding orphan daemon. Packaged onedir wiring moves to Change 3. |
| S1: Tauri `externalBin` / plugin-shell. | Poor fit: expects a single exe, but onedir needs `_internal/`. |
| S3: daemon (tray) owns Tauri. | This is just the hosted mode. It keeps the heavy Python tray as owner. |

- If a tray daemon already holds the lock, the headless sidecar exits cleanly. The shell must treat that as "attach to the existing daemon", not as an error.
- Hooks: in packaged builds, pass `CLAWD_TANK_HOOK_EXE_DIR` to the sidecar (Change 3). In dev it is unset.

### Autostart
- Use `tauri-plugin-autostart` in standalone mode only.
- Enabling it removes the legacy `ClawdTank` HKCU Run value, so there is one entry at a time.
- The Python tray's `is_stale()` re-registers its own entry if the flag goes back to Electron.
- Two UIs would collide on port 19872, so exactly one login entry must exist.

### macOS and Linux handling (unverified)
- Gate the Tauri choice on darwin and Linux. Refuse `shell=tauri` there unless `CLAWDY_TAURI_MACOS=1`, and log a warning that it is unverified (L20).
- Do not add `tauri-nspanel` or any other unverified workaround.
- No macOS/Linux CI build in Change 2. The matrix is Change 3.
- Document the unverified items in the README: click-through, permissions, fullscreen overlay, Bluetooth TCC attribution for a sidecar.
- Option A lowers exposure because it avoids selective click-through.

### Size and PR slicing
Total is about 1,900-2,100 changed lines (Rust about 600, JS/HTML/CSS about 700, Python about 150, tests about 450). Use a feature-branch chain with strict TDD. Rust uses `cargo test`, JS state uses `node --test`, Python uses `pytest`. Activate Rust with `. /o/dev/env.sh`. CI does not run tests today.

| PR | Unit | Lines |
|---|---|---|
| 1 | Shell scaffold from the spike + bridge (serde framing, `read_config`, `quit`, link, `set_status`) + Rust tests | ~380 |
| 2 | Hotbar UI v1: cells, anim-map reuse, xN badge, collapse, drag, position persistence, asset copy script, state module + node tests | ~390 |
| 3 | Permission card (queue, guard, replay, clear, nonce) + sessions popover + `set_usage` meters + `set_project_usage` list | ~390 |
| 4 | Python: `--desktop-pet` flag, parent-PID watchdog, `shell` pref, `_find_desktop_pet` Tauri branch + fallback + macOS gate, tests | ~260 |
| 5 | Standalone sidecar spawn, Job Object, single-instance, attach-when-locked | ~320 |
| 6 | Tray (Show/Hide, Launch at login, Quit) + autostart migration | ~260 |

PRs 1-4 deliver hosted mode behind the flag. PRs 5-6 are standalone mode. Each PR stands alone and is revertible.

### Risks
- **macOS click-through, permissions and fullscreen overlay** are unverified (accepted L20). Mitigation is the gate above.
- **WebView2 dependency**: Windows 10 needs a bootstrapper, which Change 3 handles.
- **Footprint was measured for one window.** Option A should keep it near that, but re-measure after PR 3. Unmeasured: the real Tauri hotbar RAM and CPU.
- **Security**:
  - The TCP bridge accepts any local process on 127.0.0.1 (same as Electron today).
  - The nonce must never reach the DOM beyond the card.
  - Tighten the CSP and scope the decide command's capability.
- **Daemon singleton and orphans**: a tray daemon plus a Tauri sidecar race on the lock, and a sidecar without a watchdog is an orphan risk holding BLE. Both are covered by PR 4 and PR 5.
- **Parity gap**: standalone mode cannot toggle hooks, BLE or brightness until the settings surface is built. Label standalone mode experimental.
- **Toolchain**: Rust and MSVC live non-standard on `O:\` (spike L4). Contributors need setup docs.
- **Two login items** if autostart migration is skipped.

### Open questions for the user (product only)
1. Should standalone mode (Tauri owns the daemon and has its own tray) be in this change, or ship hosted mode first and add standalone later? This also decides whether the settings surface is built now.
2. Is the docked-bar look (small pets in cells) acceptable, or must the pets stay big and free-floating as they are today?
3. Which edge should the bar default to: right, as in orbitbar, or the bottom, where the pets live today?
4. Are the per-agent usage meters for Codex, Kiro, OpenCode and Antigravity required on the hotbar at launch, or is Claude plus the generic `set_usage` enough until a later change?
5. Is it acceptable that Linux and macOS users stay on Electron until someone verifies Tauri there?

### Ready for proposal
Yes. Questions 1 and 2 decide the PR count and the UI scope.

### Scope correction (user, 2026-10-15)
The hotbar does NOT contain the pets. It shows information, like orbitbar: a docked, always-on-top bar with one cell per agent; clicking a cell opens a usage panel with output tokens and cost overall and per project for Today / 7 days / 30 days / this month; a menu (theme, collapse, start with system, edit config); configurable cells (`open:`, `run:`, `panel:` actions); persisted free placement and collapse to a tab. UX options A/B/C above are superseded. Pets remain separate windows. The Change 1 reader (`claude_usage.py`, today/7d/30d/month per project) and `set_project_usage` already match the hotbar's first content; Codex and OpenCode readers do not exist on the Python side yet.

### Scope decision (user, 2026-10-15)
Change 2 is the hotbar only, in Tauri. The pets stay in Electron; migrating them is a separate later change. Both runtimes coexist meanwhile. Sections above about the permission card, pet cells, Electron flag replacement and tray-spawned "hosted" pet mode no longer apply to Change 2.
