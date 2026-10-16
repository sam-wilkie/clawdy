# Proposal: Tauri info hotbar (Change 2)

## Intent

Token use and cost per project are not visible for any agent. Change 1 computes them for Claude only, and nothing displays them. Add a small information bar in Tauri, modelled on orbitbar, that covers five agents: Claude, Codex, OpenCode, Kiro and Gentle Shell from day one. Pets stay in Electron, unchanged; both runtimes coexist.

## Scope

### In Scope
1. **Python readers** next to `claude_usage.py`, all read-only:
   - Codex: `~/.codex/sessions/**/*.jsonl`
   - OpenCode: `~/.local/share/opencode/opencode.db`, opened through a SQLite `mode=ro` URI so the running app is never blocked
   - Pi/Gentle Shell: `$PI_CODING_AGENT_DIR/sessions`, else `~/.gentle-shell/agent/sessions` (`*/*.jsonl`), using the `cwd` from the `session` record and `usage` from assistant messages

   All readers use the same windows and project key as the Claude reader.
2. **Usage file**: the daemon writes `~/.clawd-tank/project-usage.json` atomically, keyed by agent, with `generated_at`. It writes on every 60 s refresh, even when nothing changed, so the file age shows whether the daemon is running. Sessions in temp dirs or outside a git repo are excluded.
3. **`hotbar/` Tauri app** (Windows verified): a docked, always-on-top bar with a right-edge default. It can be dragged across monitors, its position is saved and clamped to the usable area, and it collapses to a tab.
4. **Agent cells** (Claude, Codex, OpenCode, Kiro, Gentle Shell): clicking a cell opens a side panel (left, else right; the bar never moves).
   - The panel is plan-first: plan agents show plan limits and no money; token data, when available, shows overall and per-project Today/7d/30d/month windows. It opens on Today.
   - Only pay-as-you-go agents show cost:
     - Agent-reported cost (Gentle Shell, OpenCode): `$X`.
     - Cost estimated from the price table (Codex on an API key): Spanish copy `≈ … estimado`.
     - No price available: `no price data`.
   - Stale and missing data have their own states.
5. **Custom cells** from one JSON config:
   - `open:`: http/https only.
   - `run:`: no shell, detached.
   - `panel:`: 10 s timeout, 64 KiB stdout cap.
6. **Right-click menu**: edit config, light/dark, collapse, reload config. Single instance. There is no autostart or quit item: the tray owns the hotbar's lifetime.
7. **Tray-owned process**: the Python tray starts the hotbar with the daemon and stops it on quit, the same way it manages the Electron pet today.
   - Startup and shutdown follow the `SimProcessManager` pattern: spawn, `CLAWDY_PARENT_PID`, process-tree kill, stale-process cleanup at startup.
   - The hotbar exits if the tray process dies.
   - One preference key, `hotbar_enabled` (default true), backs a "Show hotbar" checkbox in the tray menu that starts or stops the process.
   - If the hotbar exe is missing, the tray logs a warning and carries on.
   - Startup with Windows remains the tray's existing login item (`autostart.py`).

### Out of Scope (deferred)
- Kiro token usage and Antigravity usage; Kiro plan limits are in scope. The file is keyed by agent, so adding agents later does not change its format.
- Pets, permission cards, Electron changes, tray changes beyond item 7, launching the hotbar from the headless daemon.
- Packaging and installer, CI matrix, Linux, macOS verification (Change 3).

## Capabilities

### New Capabilities
- `codex-usage-reader`, `opencode-usage-reader`, `pi-usage-reader`: per-project aggregation of tokens and cost into the shared time windows
- `project-usage-file`: atomic, agent-keyed JSON export; schema, write cadence, exclusion rule
- `hotbar-window`: placement, persistence, clamping, collapse, single instance, menu, exit when the parent process dies
- `hotbar-process`: the tray spawns and stops the hotbar, finds its exe, and exposes the `hotbar_enabled` toggle
- `hotbar-usage-panel`: five agent cells, plan limits, time windows, pay-as-you-go cost display (reported vs estimated), stale state
- `hotbar-custom-cells`: config file, `open:`/`run:`/`panel:` actions and limits

### Modified Capabilities
- None in `openspec/specs/`. The Change 1 `claude-usage-reader` spec is not archived; its exclusion rule is applied when the file is written.

## Approach

**Recommended data source: (a) a file written by the daemon.**
- It reuses the `claude_usage.py` pattern and price table.
- No port, no transport, no reconnect logic.
- The hotbar reads the file and watches its mtime.

Rejected options:
- (a') The hotbar runs a TCP server as a second `desktop_pet` transport. Data would be pushed live, but it needs a new port and a Rust bridge, too much for data that changes every 60 s.
- (b) Usage readers written in Rust. The hotbar would not depend on the daemon, but the parsers and prices would exist twice.

**Launch**: the tray owns the hotbar, mirroring how it manages the Electron pet.
- A small manager next to `sim_process.py` reuses its spawn and kill code. It finds the exe from `CLAWDY_HOTBAR_EXE`, next to `sys.executable`, or `hotbar/src-tauri/target/release`.
- On the Rust side, a thread watches `CLAWDY_PARENT_PID` and exits when that process is gone.
- The hotbar has no autostart plugin, and the headless daemon does not launch it.

**Spike reuse**: keep the `tauri.conf.json` window flags and the `core:default` capability. Drop the TCP bridge and click-through polling.

## Affected Areas

| Area | Impact |
|---|---|
| `host/clawd_tank_daemon/{codex,opencode,pi}_usage.py` | New |
| `host/clawd_tank_daemon/daemon.py`, `claude_usage.py` | Modified: file export, exclusion rule, Codex prices |
| `hotbar/src-tauri/`, `hotbar/ui/` | New |
| `host/clawd_tank_daemon/hotbar_process.py` (or a new class in `sim_process.py`) | New: spawn, kill, exe lookup |
| `host/clawd_tank_menubar/{controller,preferences,app}.py`, `__main__.py` | Modified: start/stop with the daemon, `hotbar_enabled` toggle, stale cleanup |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Codex and OpenCode field layouts not yet inspected | Med | Design verifies them against real files; fixtures; unknown records skipped |
| A locked or migrating OpenCode DB | Med | Read-only URI, short busy timeout; on failure keep the last snapshot |
| Codex model prices missing from the table | Med | Show `no price data`; add dated entries |
| macOS/Linux unverified (L20) | Med | Claim Windows only; no selective click-through is needed |
| `run:` and `panel:` start any program named in the config | Med | The config is user-owned; no shell, timeouts, output caps |
| Orphaned hotbar after the tray crashes | Med | Parent-PID watchdog in Rust plus stale-process cleanup at tray startup |
| Size ~2,050 lines | High | Chained PRs |

## Rollback Plan

Delete `hotbar/` and revert the reader and export PRs; the daemon then behaves as in Change 1. Revert the tray PR; with the hotbar exe missing, the tray already skips it. Users can also set `hotbar_enabled` to false.

## Success Criteria

- [ ] Each reader gets the exact totals per project and window from its fixture; Pi and OpenCode report their own cost (pytest)
- [ ] The file matches its schema, and temp and non-git sessions are excluded
- [ ] Clamping, config parsing and action validation have unit tests (`cargo test`)
- [ ] Tray tests (pytest, fake process factory): the hotbar starts with the daemon, stops on quit, the toggle persists `hotbar_enabled`, and a missing exe is skipped
- [ ] Manual check on Windows: bar, five agent panels, menu, focus on second launch, hotbar exits when the tray is killed

## Proposal question round (assumptions for user review)

1. ~~Only Claude at launch?~~ **Updated (r3)**: Claude, Codex, OpenCode, Kiro and Gentle Shell from day one; Kiro has plan limits only, and Antigravity is deferred.
2. ~~Independent autostart?~~ **Answered (user, 2026-10-15)**: the tray launches and stops the hotbar, and the hotbar has no autostart of its own.
3. ~~Exclude non-git sessions?~~ **Answered (user, 2026-10-15)**: excluded, as in orbitbar (sessions in temp dirs or outside any git repo are not counted). Applied once in the shared readers, not only in the file: `set_project_usage` has no consumer today (Electron ignores it), so one rule avoids two diverging totals.
4. Is 5 minutes the right point to mark the data as stale? Kept as the default assumption (5 refresh cycles of 60 s); not confirmed by the user.
