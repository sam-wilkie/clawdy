# Clawd Notification Display — TODO

## Estado actual del checkout (2026-10-13)

- [x] Retirado el mod de terminal de Claude: sin menu, activacion, fuentes ni empaquetado. Limpieza de instalaciones antiguas conserva otros plugins y hooks.

- [x] Electron: mascotas y panel para Claude Code, Codex, Kiro, OpenCode y Antigravity.
- [x] Consumo: Claude por statusLine, Codex por app-server, Kiro IDE por cache y OpenCode/Antigravity por historial (dia/mes/acumulado); Antigravity no informa costo monetario.
- [x] Reinicios concedidos de Codex con confirmacion y reutilizacion de clave ante respuestas inciertas.
- [x] npm test ejecuta la suite completa mediante node --test.
- [x] OpenCode 2.0.27: adaptador setup v2 instalado; el usuario confirmo que la mascota aparece. Protocolo/integracion/standalone: 28 pruebas aprobadas.
- [x] Etiqueta local para claude/opencode: Terminal - permisos de OpenCode; no cambia el agente.
- [x] Escritorio (2026-10-13): 43 aprobadas, sin fallos. Corregido el doble de ventana; cubiertos adaptador OpenCode v2 y etiquetas de sesion.
- [ ] Ejecutar de nuevo la suite completa del host; las cifras historicas no certifican este checkout.
- [ ] Validar bandeja + Electron reales y Antigravity con agy real.
- [x] Lista macOS actualizada: incluye antigravity-usage.js y session-labels.js.
- [ ] Construir y verificar el bundle macOS actualizado.
- [ ] Confirmar contenido de instaladores publicados y preparar entrega de cambios locales.

Detalle: [estado tecnico actual](docs/clawdy-desktop-estado-2026-10-13.md). Las secciones siguientes conservan historial; no implican disponibilidad en una release.

## Base historica (v1.4.0)

Firmware builds, flashes, and runs on the Waveshare ESP32-C6-LCD-1.47 board.
BLE advertising works, notifications can be sent and dismissed via BLE GATT writes.
23 C tests pass (with ASan+UBSan), 220 Python tests pass (14 test files).
Clawd sprite animations and notification card UI are implemented.
NVS-backed config store supports brightness and session timeout with BLE read/write.
macOS menu bar app provides daemon control, device configuration UI, and simulator toggle.
Daemon supports multi-transport (BLE + TCP simulator) with dynamic add/remove at runtime.
Simulator supports TCP listener (`--listen`) for daemon-driven operation without hardware.
Tool-aware working animations — 6 distinct Clawd animations based on Claude Code tool type.
18 animated sprites integrated into scene.c, auto-cropped to tight bounding boxes.
Multi-session display with up to 4 concurrent Clawd sprites (v2 protocol).
Session state tracking in daemon with priority-based display state computation.
Staleness eviction replaces timer-based sleep — sleep is now session-driven.
Subagent lifecycle tracking prevents sleeping during long-running agent tasks.
Session state persisted to disk — restarting the app preserves display state.
Build script (`host/build.sh`) automates simulator + py2app + bundle.
Auto-update hooks, daemon health monitoring, orphan sim cleanup, launchd auto-migration.
Firmware uses RGB565A8 pixel format + cropped sprites to fit multi-session in ~200 KB SRAM (no PSRAM).
Custom app icon. Proactive BLE reconnection with full state sync on disconnect.

---

## Antigravity + OpenCode products � adapter done, desktop labels done (real agy untested)

- [x] Antigravity adapter: `antigravity_protocol.py`, plugin installer, 139 tests passing.
- [x] Antigravity Stop/StopFailure cards now title the session by the workspace folder (not "Antigravity CLI"); product name is only a fallback (`project_fallback` flag) and the daemon never lets it overwrite a stored project. Fixed in the translator, the notify-script copy and `daemon.py`.
- [x] Desktop pet treats `antigravity` and `opencode` as first-class products: order after kiro (`AGENT_ORDER` in `desktop/main.js`), labels "OpenCode"/"Antigravity" in `renderer.js` and `dashboard.js`; `desktop/test/agent-products.test.js` covers order, labels and unknown-product fallback.
- [ ] Untested against a real `agy` on a clean Windows machine: the `.cmd` wrapper, re-install of an already installed plugin, MCP tool naming, an IDE without `agy` on PATH.
- [x] 11 pre-existing failing host tests (tests updated to the new contract; production unchanged): 10 in `tests/test_session_state.py` (`daemon.py` now adds a `sessions` key) and `tests/test_kiro_protocol.py::test_pre_tool_use_execute_pwsh_maps_to_bash` (Kiro PreToolUse now emits `permission` with wait True).
- [ ] `tests/test_daemon.py::test_ble_connects_and_reconnects_by_itself_after_a_scan_error` hangs.
- [x] npm test now runs the full desktop suite (node --test); see the current result above.
- [ ] Not verified in a real Electron window: new product labels and window ordering.

## PID-less end-of-turn sessions never expired - Fixed (option A)

- [x] Cause: `_evict_stale_sessions` skipped every `waiting` session, so an Antigravity (or PID-less Codex/Kiro/OpenCode) session resting after Stop/idle_prompt (`awaiting_prompt`) had no SessionEnd and no liveness checker and lived until a daemon restart.
- [x] OpenCode plugin installer looked for the shim at `<repo>/opencode-plugin/` (`parents[2]`) instead of `host/opencode-plugin/`, so the tray said "OpenCode Plugin Not Installed"; `resolve_plugin_source` now uses `parents[1]` (tests incl. a real-repo existence guard), PR1/PR2 wording removed from the toast and log.
- [x] Now a `waiting` + `awaiting_prompt` session with no PID and no subagents expires with the normal `_session_staleness_timeout` (600 s default, not the 90 s no-PID one). Blocked waits (permission/AskUserQuestion) and PID-backed sessions are still never time-evicted. Tests in `tests/test_session_state.py`; `test_staleness_does_not_evict_end_of_turn_waiting` now sets a PID.
- [ ] Option B: resolve the real PID (`agy.exe` / Antigravity language server) in the hook so the liveness checker works for Antigravity.

## Tray quit leaves the Electron pet running - Fixed (real tray untested)

- [x] Cause: `quit()` waited 8 s on `_shutdown_sequence()`, but its last step (`daemon._shutdown()`) lets `run()` return, which ends the loop with that coroutine still pending, so the future never completed -> `TimeoutError` -> force exit. Nothing killed the pet outside that coroutine, and `kill()` only terminated the main exe (not Electron's child processes).
- [x] `SimProcessManager.kill_sync()` (loop-independent; Windows: `taskkill /F /T /PID <our pid>`, never by image name) is called from `controller.quit()` on every path (success, timeout, dead loop). Async `kill()` also tree-kills. macOS/Linux unchanged. Tests: `test_sim_process.py`, `test_controller.py` (quit cases).
- [ ] Not verified with the real tray + Electron. Open: after an orphan survives (crash, kill -9 of the tray), the next start still waits ~5 s and fails with "Port still in use"; needs a stale-pet cleanup by pid file (not by image name).

## Permission bubble (desk window Allow/Deny) — simulator side Implemented

- [x] `simulator/sim_permission.c/.h`: parses `permission_request` / `permission_clear` on the socket thread (validated, mutex queue), FIFO bubble on the LVGL top layer (8x8 unscii font, ASCII-sanitised text, 2-line summary, "+N waiting"), Allow/Deny buttons, 400 ms click guard (restarts for every newly shown request), decision `{"event":"permission_decision",id,nonce,decision}` sent only from a real left press+release on a button; send failure keeps the bubble; daemon disconnect clears all.
- [x] Desk hit-test: button rectangles return `SDL_HITTEST_NORMAL`, the rest stays draggable. Windows: desk window is `WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW`; other windows are non-activating only while a bubble is up; hidden window is auto-shown WITHOUT activation and re-hidden when the last request resolves.
- [x] Test hooks in `--events`: `permission <id32> <nonce16> "proj" "tool" "summary"`, `permission_clear <id>`, `click allow|deny|<x> <y>` (logical), `clickw <x> <y>` (window px), `quit`.
- [x] Verified headless (screenshots with/without `--desk`), fake-daemon TCP E2E, and the real daemon + `clawd-tank-notify` chain with in-sim injected clicks (hook printed allow / deny JSON).
- [x] Bubble made compact after the first manual test: 176x52 logical (352x104 px at scale 2, 528x156 at scale 3), centred above the crab; buttons 80x12 logical; `project > tool` header, 2-line summary, "+N" counter. Desk mode defaults to `--scale 2`; `ver-sim.bat` has a separate DESKSCALE (default 2).
- [x] Desk window snapped back after a drag. Root cause: SDL's Win32 shaped-window code (WM_GETMINMAXINFO -> Win32_ResizeWindowShape) parks the window at (-1000,-1000) when a drag starts and the next SDL_SetWindowShape() restores the PRE-drag position. Fix: on Windows the desk window is a plain window and the shape is a region set with SetWindowRgn (`desk_set_region_win32`); aspect-ratio enforcement and the 328x180 minimum size no longer apply to the desk window. Reproduced and verified with the in-sim hooks `winlmb`/`winmove`/`winlog`/`winsize`.
- [ ] Unexplained: the TCP connection from a fake daemon dropped ~53 s into a manual run. Not reproduced (27 s soak with 28 simulated drag starts + bubbles: connection intact, no crash).
- [ ] Manual check needed on a real desktop: real mouse click on the bubble in `--desk`, keyboard focus stays in the terminal, dragging the crab still works.


## v2 crab art on the device (15 anims) — Implemented (firmware target build + full v1 re-check pending)

- [x] 15 mapped anims regenerated from v2 SVGs at scale x3 via `tools/regen_v2_sprite.py`; `*_FRAME_MS` matched to v2 fps, `.looping` preserved, uniform `y_offset=-21`, `GRASS_HEIGHT` 14→24 in `scene.c`.
- [x] Parametrized contract+heap test (dims, exact-pixel RLE decode, 73 KB ceiling), `frame_ms` simulator-capture test, and 7-header byte-identical no-regression guard — all green. SDL2 simulator builds clean.
- [x] `tools/svg2frames.py` `.resolve()` Windows fix committed; pipeline runs under system Python 3.11.
- [x] Render scale frozen at x3 after WAKE simulator review (x4 rejected for the 73 KB heap ceiling).
- [ ] Build the firmware target: `idf.py build` was NOT run (idf.py not on PATH). The ESP32-C6 compile of `scene.c` + the 15 regenerated headers is UNVERIFIED — must build in an ESP-IDF 5.3.2 environment before flashing.
- [ ] Re-check the remaining 5 v1 anims under the taller 24px grass band in the simulator: disconnected, going_away, wizard, beacon re-checked (aligned); mini_crab is a grass-independent HUD icon; walking + juggling could not be captured in isolation (transient internal anims) but share the same BOTTOM+y_offset mechanism with untouched v1 offsets, so low risk.
- [ ] Not pushed / no PR opened — completed locally on branch `personal` (commits 501457b, 5028c08, 60f5efd, b4f4023, 7d80e27, e61dba2).

### Follow-up (next change — do not do now)

- [ ] Design the 7 missing v2 SVGs (beacon, wizard, juggling, walking, going_away, disconnected, mini_crab) so all device anims can be v2. The existing 15 v2 SVGs were authored with Claude Opus 5.5 (not the Gemini pipeline). Once the 7 SVGs exist, porting them is trivial via the proven `tools/regen_v2_sprite.py` + the parametrized contract test.

## BLE auto-reconnect (scan error killed the sender) — Fixed (live hardware untested)

- [x] Root cause: a first-scan `BleakError` (macOS TCC check still running at app start) escaped `_connect_until_found` and ended `_transport_sender` silently. Scan errors are now retried with back-off, and `_transport_sender` restarts after a crash (logged with traceback).
- [x] Log lines: scan failures (WARNING, first and every 6th), "not found after N scans" (INFO, every 6th).
- [ ] Restart the installed app with the board in range and check the log: first scan may log `BLE scan failed ... retrying in 1s`, then `Found Margarita` and `Transport 'ble' connected` with no click on Reconnect.
- [ ] Switch the board off and on (or walk out of range) and check it reconnects by itself within a few seconds.
- [ ] Known leftover: `ClawdBleClient.disconnect()` awaits bleak's `disconnect()` with no timeout (only the manual Reconnect path uses it on a live link).

## Desk-pet simulator window (`--desk`) — Implemented (interactive window untested)

- [x] `scene_enable_desk_mode()` hides the scenery and paints the screen with the sprites' key color `0x18C5`; `sim_display` makes the window borderless, always on top, no LED border, and shapes it to the sprites with `SDL_SetWindowShape`. Device path unchanged (the flag is never set on the device).
- [x] Verified headless: `--headless --desk` screenshots show only the crab over the key color; normal mode still renders sky, hills and grass.
- [x] Real window on Windows (screen capture): the window is shaped and only the sprite shows. It needed `SDL_CreateShapedWindow` (`SDL_SetWindowShape` fails on a normal window), which the first version missed.
- [ ] Check click-through outside the sprite and drag on the real window.
- [x] Tray toggle "Floating desk pet" (Windows pystray, top-level item right after Simulator; mirrored in rumps_view.py as "(untested on macOS)"). `controller.toggle_sim_desk()`: ON persists `sim_desk_mode`, enables the simulator and restarts it via `SimProcessManager(desk=True)` (args `--listen <port> --desk`, visible, no `--hidden`/`--pinned`); OFF persists false and stops AND disables the simulator (`sim_enabled=false`, no fallback to the normal window; Simulator > Enabled brings that back). One sim process/port, so the two modes are exclusive; Simulator > Enabled OFF also clears desk mode. Show Window / Always on Top are greyed out and ignored in desk mode. `sim_desk_mode` saved true => the crab starts automatically at tray start. Run the tray from source with `ver-tray.bat`.
- [ ] Manual check needed: click the real tray item on Windows (unit tests use fakes only); packaged PyInstaller flow unchanged (it already bundles the simulator exe).
- Known limits: notification cards and the usage/time HUD are hidden in desk mode.

## Mod de terminal Claude - retirado (2026-10-13)

La funcion fue eliminada. Las notas anteriores quedan en el historial de Git; Electron y los hooks de actividad de Claude continuan disponibles.

## Mod de terminal Claude - retirado (2026-10-13)

La funcion fue eliminada. Las notas anteriores quedan en el historial de Git; Electron y los hooks de actividad de Claude continuan disponibles.

## statusLine bridge — Implemented (Windows paths untested on real Windows)

- [x] Bridge script (`hooks.STATUSLINE_BRIDGE_SCRIPT`) caches `rate_limits` atomically and chains the user's original statusLine.
- [x] `install_hooks()` / `uninstall_hooks()` wire and restore `statusLine`; `are_hooks_installed()` reports outdated until it is wired.
- [x] `margarita-statusline.exe` added to the PyInstaller spec and the release workflow check.
- [x] macOS/Linux run `hooks.STATUSLINE_BRIDGE_SH` (plain `sh`, no python3) instead of the Python bridge; the original command is mirrored to `statusline-original.txt`, and an install wired to `statusline_bridge.py` is migrated on start.
- [x] Windows: the original statusLine is chained through Git Bash (`CLAUDE_CODE_GIT_BASH_PATH`, else the bash next to `git`) instead of cmd.exe, falling back to cmd.exe; only the selection is unit-tested (platform strings), not run on Windows.
- [ ] Verify the frozen Windows build end to end (statusLine run by Claude Code on Windows, including the Git Bash chaining).

## Phase 1 new crab animations — Implemented (not yet flashed)

- [x] **happy on SubagentStop** — when a subagent of a visible session finishes, v2
  transports get a `set_sessions` with that slot = `happy`, immediately followed by the
  real state (forced broadcast) which the firmware keeps as the slot's fallback. v1: skipped.
- [x] **wake** (new sprite, 12f oneshot) — firmware-side: `ui_manager.c` plays it on slot 0
  when `set_sessions` (or a v1 non-sleeping `set_status`) arrives while the scene shows the
  sleeping crab; skipped while slot 0 walks to a new position.
- [x] **low_battery** (new sprite, 48f @6fps) — an `idle` session shows it when the 5h or
  weekly usage is >= `LOW_BATTERY_USAGE_PCT` (90); a usage poll re-broadcasts the display state.
- [x] **hat_mishap** (new sprite, 42f @6fps) — a `tool_failed` on WebSearch/WebFetch shows it
  instead of `confused`; other tool failures stay `confused`.
- [x] **Multi-session oneshot protection** — the multi-session `set_sessions` path no longer
  cuts a playing oneshot (matches the single-session path).
- [x] **Protocol v3 gating** — firmware reports protocol version 3 (v2 + `happy`/`low_battery`/`hat_mishap` in `set_sessions`); the simulator counts as v3. For v2 transports the daemon
  maps `low_battery`→idle, `hat_mishap`→confused and skips the `happy` oneshot
  (`downgrade_display_state`, `MIN_PROTOCOL_FOR_PHASE1_ANIMS`), so old firmware no longer drops crabs.
- [ ] Flash the device and check the four animations on hardware. Old (v2) firmware now gets
  downgraded names from the daemon, so host and firmware can be updated separately.

## Phase 2: "turn finished, waiting for your reply" animation — Planned (needs the flashing PC)

Today the end of a turn plays the `happy` oneshot and then the crab falls back to `idle`,
so it looks the same as "nothing is happening". Add a distinct, persistent state for
"Claude finished and is waiting for the next prompt". Not to be confused with the existing
`waiting` session state (blocked on AskUserQuestion / PermissionRequest).

Proposed behaviour:

- [ ] New sprite `waiting_reply`: the crab looks at the user, taps a foot and shows a `!`
  (loop, no oneshot). Draw it as `assets/svg-animations/clawd-waiting-reply.svg` on the
  15x16 grid of `clawd-static-base.svg`, then run the sprite pipeline from CLAUDE.md
  (`tools/svg2frames.py` → `tools/png2rgb565.py` → `tools/crop_sprites.py`, output
  `firmware/main/assets/sprite_*.h`) and register the animation in `scene.c` / `ui_manager.c`.
- [ ] Daemon: after the `happy` oneshot on `Stop`, the session state becomes `waiting_reply`
  and stays until the next `UserPromptSubmit` (then `thinking`). It must be exempt from
  staleness eviction the way `waiting` is, and evicted only by the PID-liveness check.
- [ ] Protocol: bump the firmware protocol version to 4 (`ble_service.c`) and add the name
  to `PHASE1_ANIM_FALLBACKS` (`waiting_reply` → `idle`) so v2/v3 firmware keeps working
  (`downgrade_display_state`, `MIN_PROTOCOL_FOR_...`).
- [ ] Flash the board and check it on hardware (the simulator compiles the same sources, so
  it can be checked there first).

## Windows Claude PID resolution — Complete

- [x] **Hook resolves Claude's PID on Windows** — `_find_claude_pid()` (NOTIFY_SCRIPT,
  mirrored in `pid_resolver.py`) walks one Toolhelp32 snapshot for the first `claude.exe`
  ancestor. Windows sessions now keep the normal staleness timeout and are evicted by the
  PID-liveness checker when Claude exits, instead of vanishing 90 s after going idle.
  No ancestor (node-hosted install) → `None`, never the short-lived shell's PID.
  Limitation: a PID reused within one 30 s liveness tick keeps the session until the
  normal timeout (creation time is not compared).

## Code-review hardening (attention-hooks branch) — Complete

Multi-agent review of the attention-hooks work surfaced 15 findings; fixes:

- [x] **Don't staleness-evict `waiting` sessions** — a session blocked on AskUserQuestion/
  PermissionRequest emits no events, so time-based eviction wrongly dropped the alert
  while the user was away. Now excluded from staleness eviction; PID-liveness still
  evicts a dead Claude process.
- [x] **Installer self-heals / prunes superseded groups** — `install_hooks()` now drops our
  OWN prior hook groups before re-appending the current config, so a changed matcher
  no longer leaves a stale wildcard group firing on every tool. `are_hooks_installed()`
  reports outdated when a leftover our-group sits under an unexpected matcher.
- [x] **Installer crash-guard + precise command match** — tolerates malformed `{"hooks": null}`
  groups (no TypeError); matches our notify command by exact-path/prefix, not substring
  (a user wrapper containing the path is no longer mistaken for ours).
- [x] **`waiting` outranks subagents** — a session with active subagents that hits a
  permission/question prompt now shows the alert instead of being masked by `conducting`.
- [x] **No phantom resurrection** — `permission`/`tool_failed` no longer create a missing
  session (matches `tool_done`), so a late event after SessionEnd can't revive a ghost.
- [x] **v1 alert priority** — on v1 transports `alert` (needs-you) now outranks working/
  thinking instead of being buried.
- [x] **Cleanup** — shared `ASK_USER_QUESTION_TOOL` constant (single source of truth),
  `_enter_state` helper removes the copy-paste state branches, `sim_main.c` `--capture-anim`
  learns `alert`, and a cross-validation test guards NOTIFY_SCRIPT↔protocol.py drift.
- Verified NOT defects / accepted limitations: the `alert` sprite loops seamlessly
  (frame 39 ≈ frame 0 — captured and checked), so no firmware change; a PermissionRequest
  alert may persist into the approved tool's run (no "granted" hook exists in Claude Code);
  `tool_failed` intentionally reuses the `confused` animation.

## "Waiting for input" alert + PostToolUse — Complete

- [x] **AskUserQuestion → waiting/alert** — When Claude shows the multiple-choice
  dialog (`AskUserQuestion` tool), its `PreToolUse` now maps to a distinct
  `waiting` session state that renders the `alert` Clawd animation, instead of the
  generic `typing` it shared with real work. Claude is blocked on the human, so it
  now looks like it.
- [x] **PostToolUse hook (scoped to AskUserQuestion)** — New `PostToolUse` hook,
  registered with `matcher: "AskUserQuestion"` to keep device event/BLE traffic
  minimal. Emits a `tool_done` daemon event that clears the `waiting` alert back to
  `thinking` the moment the user answers. The daemon-side handler is generic, so the
  matcher can be broadened later with zero code change.
- [x] **`alert` anim string parsing** — Added `"alert"` → `CLAWD_ANIM_ALERT` to both
  `ble_service.c` and `sim_ble_parse.c` `parse_anim_name()` (it was previously
  unmapped). v1 transports map the `alert` anim to the `confused` needs-attention
  status. Notify script version bumped to `2026-05-30-posttooluse` (auto-reinstalls).
- [x] **Non-clobbering hook installer** — `install_hooks()` now MERGES our hooks into
  the user's Claude Code settings instead of `dict.update()` replacing whole event
  keys. For each event+matcher we manage, our hook group is appended only if absent;
  the user's own hooks (and other settings keys) are never modified or removed.
  Idempotent. `are_hooks_installed()` is now matcher-aware so a new/changed matcher is
  correctly detected as outdated. (`tests/test_hooks_install.py`, 12 tests.)
- [x] **PermissionRequest → waiting/alert** — When Claude is blocked waiting for the
  user to approve a tool, the session enters the same `waiting`/`alert` state as
  AskUserQuestion. No "granted" hook exists and `PreToolUse` precedes it, so the alert
  clears on the next `tool_use`/`Stop`/`UserPromptSubmit`. Fires only when a permission
  dialog actually appears (auto-approved tools don't trigger it).
- [x] **PostToolUseFailure → confused** — A genuine tool error (not a non-zero shell
  exit) maps to the `confused` state — a transient "that didn't work" snag, lighter
  than the API-error `error`/dizzy state. No notification card; clears on the next
  event. Both new hooks reuse existing states/animations — no firmware/v1 changes.
  Notify script version → `2026-05-30-permission-toolfailure`.

## Working Animations (v1.1.0) — Complete

- [x] **Session state tracking in daemon** — `dict[session_id → state]` with `_compute_display_state()` priority resolution. States: registered → thinking → working → idle → confused. Display priority: working_N > thinking > confused > idle > sleeping.
- [x] **Intensity tiers** — 1 session working = Typing animation, 2 sessions = Juggling, 3+ sessions = Building.
- [x] **Hook protocol expansion** — New hooks: SessionStart, PreToolUse, PreCompact. Hook discriminator field on existing add/dismiss events for daemon-side session state differentiation.
- [x] **6 new sprite animations** — thinking (32f), typing (12f), juggling (10f), building (8f), confused (48f), sweeping (12f, oneshot). All 180×180px @ 8fps. Generated from SVG sources via svg2frames.py + png2rgb565.py pipeline.
- [x] **Fallback animation mechanism** — `scene_set_fallback_anim()` allows oneshots (alert, happy, sweeping) to return to the current working animation instead of always IDLE.
- [x] **set_status BLE/TCP action** — `display_status_t` enum with string-to-enum mapping in both firmware and simulator JSON parsers.
- [x] **Session-driven sleep model** — Timer-based sleep removed from firmware. Sleep is now daemon-driven: no sessions = sleeping. Staleness eviction (configurable timeout, default 10min) handles ungraceful session termination.
- [x] **PreCompact sweeping** — Daemon sends sweeping oneshot followed by computed state as fallback.
- [x] **Hook migration detection** — `are_hooks_installed()` checks all required hooks, not just any. Install button always updates to latest.
- [x] **Menu bar "Session Timeout"** — Renamed from "Sleep Timeout", wired to daemon staleness timeout.

## Sprites & Animations (v1.0.0) — Complete

- [x] **All 5 SVG animations converted to C sprite headers** — idle (96f/135×135), alert (40f/135×135), happy (20f/120×120), sleeping (36f/120×120), disconnected (36f/150×120). Frame buffer cap raised from 48→96. All `#if HAS_*_SPRITE` guards removed from `scene.c`. Alert and happy remain non-looping (one-shot). Idle, sleeping, disconnected loop.

## UI/UX Design (v1.0.0) — Complete

- [x] **Notification entry animation** — fade animation implemented (300ms ease-out via `lv_anim` + `lv_obj_set_style_opa`). Fade-in on show, fade-out with hide callback on dismiss. Instant path preserved for disconnect/clear.
- [x] **Transition animation** — full-screen new notification → compact list view. New notification triggers a 2.5s hero/expanded card view (fills the notification panel), then animates via `lv_anim` with `lv_anim_path_ease_in_out` over 350ms down to the compact list height. Implemented in `notification_ui.c` via `notification_ui_trigger_hero()` (called from `ui_manager.c` on `BLE_EVT_NOTIF_ADD`). Auto-rotation and repeat-hero on rapid new notifications are both handled correctly.
- [x] **Text truncation and scrolling** — featured card uses `LV_LABEL_LONG_SCROLL_CIRCULAR` marquee for both project name and message. Compact list uses `LV_LABEL_LONG_DOT` ("..."). Manual `snprintf` truncation removed.

## Simulator Improvements (v1.1.0) — Complete

- [x] **Default scale changed to 2x** — Window opens at 640×344 instead of 960×516.
- [x] **`--pinned` flag** — Always-on-top mode via `SDL_SetWindowAlwaysOnTop`.
- [x] **Auto-focus on launch** — `SDL_RaiseWindow` brings window to front.
- [x] **Shutdown freeze fix** — Client socket closed during shutdown to unblock `recv()` in listener thread.

## Python Host Hardening (v1.0.0) — Complete

- [x] **Socket length framing** (`socket_server.py`) — switched to newline-delimited messages; server uses `readline()`, sender appends `\n`
- [x] **`sys.exit(1)` in hook** (`clawd-notify`) — changed to `sys.exit(0)` with explanatory comment; notifications are best-effort
- [x] **Log file context manager** (`clawd-notify`) — `open()` now in a `with` block; handle closed even if `Popen` raises
- [x] **Broad `except Exception`** (`socket_server.py`) — `JSONDecodeError` caught separately with `logger.error`, `TimeoutError` caught explicitly with `logger.warning`, remaining unexpected errors use `logger.exception()` for full traceback

## Testing Improvements (v1.0.0) — Complete

- [x] **Add sanitizers to C test Makefile** — `-fsanitize=address,undefined -Werror` added to CFLAGS and LDFLAGS; 18/18 tests pass clean
- [x] **Test `_replay_active`** — 4 tests: sends all active, empty store, skips unknown events, concurrent mutation safe
- [x] **Test BLE write failure → reconnect → replay path** — 2 tests: single and multi-notification replay after write failure
- [x] **Test `cwd=""`** (empty string explicitly) — verified `Path("").name` triggers the `"unknown"` fallback

## Simulator-Daemon Bridge (v1.0.0) — Complete

- [x] **TCP socket listener in simulator** — background pthread with mutex-guarded ring buffer queue, newline-delimited JSON protocol matching BLE GATT format. `--listen [port]` CLI flag (default 19872). Shared JSON parser (`sim_ble_parse.c`) mirrors firmware's `parse_notification_json`.
- [x] **Multi-transport daemon architecture** — `TransportClient` Protocol, `SimClient` TCP transport, per-transport queues and sender tasks. `--sim` / `--sim-only` CLI flags. Dynamic `add_transport`/`remove_transport` methods.
- [x] **Per-transport observer status** — `on_connection_change` includes transport name. Menubar shows per-transport status lines (BLE/Simulator: Connected/Connecting...).
- [x] **Simulator toggle in menubar** — "Enable Simulator" checkable menu item with preference persistence (`~/.clawd-tank/preferences.json`). Dynamically adds/removes sim transport at runtime.
- [x] **Initial replay on connect** — `_transport_sender` replays active notifications after initial connect, so dynamically-added transports show existing notifications.
- [x] **Stop hook support** — `protocol.py` handles Stop hook event to show "Waiting for input" notification immediately when Claude stops.

## Code Quality (v1.0.0) — Complete

- [x] **Document `_lock_t` locking intent** (`ui_manager.c`) — comment explaining the lock covers both `rebuild_ui()` and `lv_timer_handler()`
- [x] **Comment `display_init()` return** (`main.c:42`) — return value intentionally discarded; LVGL tracks default display internally
- [x] **LVGL mutex migration** — added TODO comment in `ui_manager.c` noting the `lv_lock()`/`lv_unlock()` migration consideration and flush-ready integration concern

## Subagent Tracking (v1.2.0) — Complete

- [x] **SubagentStart/SubagentStop hooks** — New hooks registered and forwarded to daemon via the hook handler script.
- [x] **Per-session subagent tracking** — `subagents: set[agent_id]` tracked per session in daemon state dict.
- [x] **Eviction suppression** — Sessions with active subagents are never evicted by staleness checker.
- [x] **Display state integration** — Sessions with active subagents count as "working" in display state computation, preventing Clawd from sleeping during long subagent tasks.

## Session State Persistence (v1.2.0) — Complete

- [x] **Atomic session state save/load** — `save_sessions()`/`load_sessions()` in `session_store.py` serialize session state dict to `~/.clawd-tank/sessions.json` with set↔list conversion. Atomic writes via temp file + `os.replace`.
- [x] **Smart persistence** — Session state saved only on structural changes (state transitions, subagent add/remove), not on every `last_event` timestamp update. Reduces disk writes during heavy tool use.
- [x] **Daemon startup recovery** — Loads saved sessions on init with immediate staleness eviction. Restarting the menu bar app immediately shows correct animation for running Claude Code sessions.

## Daemon Resilience (v1.2.1) — Complete

- [x] **Auto-update hooks on startup** — Hooks are checked and updated automatically on app launch when outdated, removing the need for manual "Install Hooks" clicks after code updates.
- [x] **Daemon thread crash logging** — Daemon thread exceptions are caught and logged instead of dying silently. Periodic health check timer detects dead daemon and shows disconnected icon.
- [x] **Orphaned sim process cleanup** — On startup, orphaned simulator processes on the listen port are identified by name and killed instead of being connected to.
- [x] **Display state sync on replay** — `_last_display_state` is updated after transport replay to prevent duplicate broadcasts.
- [x] **Proactive BLE reconnection** — Transport sender loop detects dropped connections on each 1s timeout and immediately reconnects with full state sync (time, protocol version, notifications, sessions) instead of waiting for the next hook message.

## Multi-Session Display (v1.3.0) — Complete

- [x] **Multi-session display** — Up to 4 concurrent Clawd sprites with per-session animations. Protocol v2 `set_sessions` action with stable UUIDs. Overflow badge shows "+N" beyond `MAX_VISIBLE=4`.
- [x] **Walk-in animation** — New sessions enter from offscreen with a walking sprite. Existing sessions reposition with walk animations on layout change.
- [x] **Going-away burrowing animation** — Exiting sessions play a burrowing animation. Remaining sessions defer repositioning until burrowing completes.
- [x] **HUD subagent counter** — 2x-scaled mini-crab icon with pixel-art bitmap font shows active subagent count. Overflow badge anchored to right edge.
- [x] **Per-session sweeping** — `PreCompact` sends sweep animation only to the compacting session (v2), global sweep preserved for v1 fallback.
- [x] **Protocol version negotiation** — BLE GATT characteristic exposes protocol version (v2). Daemon reads on connect, selects v1 `set_status` or v2 `set_sessions` per-transport.
- [x] **`query_state` TCP action** — Debug introspection returning JSON with slot states, animations, and positions.
- [x] **Simulator window improvements** — Continuous float scaling, aspect ratio enforcement (328:180), uniform LED border rendering, borderless/resizable window with integer pixel scaling.
- [x] **Custom app icon** — macOS app icon with Clawd pixel-art crab design. SVG source and full iconset in `assets/`.

## Sprite Auto-Crop & Firmware Memory Optimization (v1.3.0) — Complete

- [x] **Auto-crop sprite pipeline** — `tools/crop_sprites.py` reads existing C headers, decodes all frames, finds tight bounding box, applies symmetric horizontal + free vertical crop, re-encodes RLE, writes headers in-place. `tools/analyze_sprite_bounds.py` for analysis.
- [x] **All 14 sprites cropped** — Frame buffer savings: 1194 KB → 368 KB (69%). Largest session sprite: confused 152x113 (50 KB). Idle: 72x51 (11 KB). Walking: 60x40 (7 KB).
- [x] **RGB565A8 firmware pixel format** — Frame buffers use 3 bytes/pixel (LVGL native-with-alpha for 16-bit display) instead of 4 bytes/pixel ARGB8888. New `rle_decode_rgb565a8` decoder.
- [x] **Firmware slot limits** — `MAX_VISIBLE=4`, `MAX_SLOTS=6` on firmware (no PSRAM). Simulator retains `MAX_SLOTS=8`.
- [x] **y_offset adjustments** — All `anim_defs` y_offset values recomputed: `new = old - bottom_rows_removed`.
- [x] **Firmware build fixes** — `pixel_font.c` added to CMakeLists, format specifier warnings fixed, unused code suppressed.
- [x] **Heap diagnostics** — Free heap logged at boot. OOM logging in `ensure_frame_buf`.
- [x] **PSRAM correction** — ESP32-C6FH8 has no PSRAM. Removed bogus settings from `sdkconfig.defaults`, corrected CLAUDE.md.

## Desktop pet: grooving = subagents working — Implemented (live pet untested)

- [x] Verified in the Claude Code hooks docs: PreToolUse/PostToolUse fired inside a subagent carry `agent_id` + `agent_type` (under the PARENT `session_id`); the main agent's calls have neither.
- [x] `protocol.py` + embedded `NOTIFY_SCRIPT` (`NOTIFY_SCRIPT_VERSION` 2026-10-11-subagent-agent-id) add `agent_id` to tool_use/tool_done/tool_failed/permission only when present.
- [x] Daemon: a subagent's tool event no longer overwrites the main session's state/tool_name (it only refreshes liveness). A subagent permission still raises the alert.
- [x] `products[].bg` = running subagents (omitted when 0), sim/pet transport only; `anims`/BLE payloads unchanged.
- [x] Pet: `renderer/anim-map.js` (`mapAnim`, tested with `npm test`): main-agent tool/thinking/alert > conducting (first 4s of an Agent dispatch) > grooving (bg>0) > idle. `fake-daemon.js` demo exercises it.
- [ ] Manual check in the live pet with a real Claude session running subagents (conducting -> grooving, main-agent tool wins).
- [ ] Open: a subagent tool_use still cancels the parent's pending permission bubble (pre-existing per-session cancel; now could be made agent-aware).

## Desktop pet: no_credits (broke crab) — Implemented (live pet untested)

- [x] `products[].exhausted: true` (omitted when false, pet/sim transport only): set when a product has an `out_of_credits` session and its final `anim` is still `low_battery`, so an active/alert/thinking/error/conducting sibling session keeps the pet on that. `anims`, BLE and v2 downgrade unchanged (out_of_credits stays `low_battery`/idle for hardware). Tests in `host/tests/test_session_state.py`.
- [x] `anim-map.js` `mapAnim(name, bg, conductMs, exhausted)`: alert > exhausted -> `no_credits` > the rest. New art `renderer/assets/clawd-no-credits-v2.svg` (declined card with blinking red X slides over the head, shrug, flapping empty pockets, tear), registered in `renderer.js` STATES; Codex window reuses the low-battery cloud. `fake-daemon.js` cycle and scenario include it. `npm test`: 6 pass.
- [ ] Manual check in the live pet with a real exhaustion (or `fake-daemon.js`), and a Codex window.
- [ ] Optional: dedicated Codex cloud art for no_credits.

## Out-of-credits detection — Part A implemented, Part B proposal only

- [x] **Claude Code `StopFailure` exhaustion** — `protocol.classify_exhaustion()` matches `error`/`stop_reason`/`error_type`/`error_details` (case-insensitive: credit, quota, billing, insufficient, usage limit, `rate_limit` token). Match -> card "Out of credits" / "Usage limit reached" (red alert flash kept) and session state `out_of_credits`, which renders as `low_battery` (v2 transports downgrade it to idle). No firmware change. Verified from the Claude Code hooks docs: StopFailure error types include `billing_error` and `rate_limit`; assumed: the exact payload field names beyond `error`.
- [x] **Kiro exhausted credits**: kiro_log_watcher.py reads session creation and UsageLimitReachedError from local logs, producing normalized session/exhaustion events. Dedicated tests exist; live validation remains pending.
- [ ] **Codex exhausted credits animation**: account-limit queries in the panel are implemented; a verified end-to-end exhaustion signal for the pet still needs real payload validation.

## Future Considerations (Out of Scope)

- Physical button interaction (dismiss notifications from the device)
- Multiple host device support (pairing with more than one Mac)
- OTA firmware updates over WiFi
- Per-session project name display during working animations

### Codex alert stuck + tool aliases
- [x] Daemon clears the permission alert when the wait resolves: allow -> working, deny / hook hangup -> thinking (broadcast + persist); AskUserQuestion and newer state (question, Stop) are never overwritten. Timeout / no pet keeps the alert; Codex-only fallback expires it after `CODEX_PERMISSION_ALERT_SECONDS` (120s) via `_evict_stale_sessions`.
- [x] `CODEX_TOOL_ALIASES` (daemon + embedded notify script, drift test): exec_command->Bash, web_search/webrun->WebSearch, view_image->Read. `update_plan` / `request_user_input_async` left passthrough on purpose.
- [ ] Verify with a real Codex that the hook process is killed when the permission is answered in Codex's own UI (assumed for the hook-hangup path).
