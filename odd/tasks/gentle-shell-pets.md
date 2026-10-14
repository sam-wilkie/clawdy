# Pets for gentle-shell (Pi) sessions

Branch `feat/gentle-shell-pets` off `feat/hotbar-daemon` (worktree `O:\Proyectos\_gshell`). Ports the OpenCode integration to a new product `pi`. Permissions included.

## Specs

- S1 The user asked: "quero que los pets aparezcan con gentle-shell". Pi sessions show up on the pets as product `pi`.
- S2 A Pi session is identified by the `pi:` session prefix. States: registered, thinking, working, waiting, idle, ended. Ending a session removes its slot.
- S3 Pi tool permissions block on the pet and resolve like OpenCode's: allow or deny. Denying blocks the tool call in Pi. No pet connected means no block (answer `none`, Pi decides as usual).
- S4 Installer: writes one extension file to `<agent-dir>/extensions/clawd-tank.js` (agent dir from `PI_CODING_AGENT_DIR`, default `~/.gentle-shell/agent`). Uninstall removes exactly that file. Other extensions are never touched.
- S5 Pet art: `pi` uses the default monster art. No new art in this change.
- S6 Preservation: Claude, Codex, Kiro, OpenCode and Antigravity behave exactly as before. Their tests stay green.
- S7 Pi-side code never throws into Pi. Failing to reach the daemon is silent (fire-and-forget), as the OpenCode plugin does.

## Tasks

- T1 S2,S5 · `pi_protocol.py` translator + `pi:` prefix · inline · RED observed (module missing), GREEN pending
- T1b S2,S5 · desktop `AGENT_ORDER`/`AGENT_NAMES` in `desktop/main.js`, `SESSION_AGENT_PREFIXES` in `daemon.py` · inline · pending (edits existing symbols: gitnexus_impact first, or record unavailable)
- T2 S2,S3 · daemon integration tests (lifecycle, permission block and none) · inline · pending
- T3 S1 · notify script accepts `pi` and translates it; embedded NOTIFY_SCRIPT copy kept in sync · inline · pending
- T4 S4,S7 · Pi extension `host/pi-extension/clawd-tank.js` + install/uninstall/are_installed in `hooks.py` · inline · pending
- T5 S1,S6 · tray toggle + packaging entry (PyInstaller datas) · inline · pending
- T6 S6 · docs (`TODO.md`, this file), full host suite, commit · inline · pending

## Log

- L1 (user) "quero que los pets aparezcan con gentle-shell"
- L2 (user) chose "Estados + permisos" for scope after the Pi docs review (extension events and `tool_call` blocking confirmed in `docs/extensions.md`).
- L3 (evidence) Exploration of the OpenCode integration came from the working tree of `feat/hotbar-usage-reader`, not from this branch. Each path:line is re-checked here before editing.
- L4 (plan review) todo projection re-checked against the doc: T1b added (desktop/daemon symbols), gitnexus caveat carried to T6. Desktop pet art stays monster (S5), so no renderer change.
- L5 (evidence) Full host suite: 1259 passed, 49 skipped, 1 deselected (known hanging BLE test). Desktop suite: 44/44 (`NODE_PATH` to main node_modules for sql.js).
- L6 (evidence) Real PyInstaller build: exit 0; `dist/Clawdy/pi-extension/clawd-tank.js` and `Clawdy.exe` present. Runtime with a real Pi session NOT run.
- L7 (not done) gitnexus_impact / detect_changes not run: tool unavailable in this session. Reported as a gap.
- L8 (not done) macOS rumps item verified by py_compile and unit-free diff only.
- Nothing committed: waiting for explicit user request.
