# Proposal: Shell-agnostic daemon groundwork for the Tauri hotbar (Change 1)

## Intent

The hotbar's first content is Claude Code token usage and cost per project. No reader for that data exists. The daemon also depends on the tray: hook paths come from the tray exe (`hooks.py:1107-1166`), and preferences/hook install run only in the tray controller (`daemon.py:1674-1690` handles only `--sim*`). Change 1 moves this work into the daemon. It ships value to Electron now and works even if the Tauri spike fails.

Components: **host** (daemon, hooks). **desktop**: consumer only, optional. **firmware/simulator/tools**: untouched.

## Scope

### In Scope
1. **Usage reader**: read-only parse of `~/.claude/projects/**/*.jsonl` (`cwd`, `message.model`, `message.usage.*`). Reports input/output/cache tokens and estimated cost per project for today / 7d / 30d / calendar month. Uses a built-in price table with sources. No network.
2. **Additive action `set_project_usage`**: sent only to `desktop_pet` transports. Never sent to BLE or the SDL sim. (`set_usage` already exists for rate-limit percentages and stays unchanged.)
3. **Hook path resolution**: notify/statusline commands come from an explicit location instead of `sys.executable` at import time. Hooks that point at a missing exe are re-pointed on startup.
4. **Headless parity**: `python -m clawd_tank_daemon.daemon` applies `preferences.json` and installs/updates hooks on startup when it owns the daemon lock (opt-out flag `--no-install-hooks`, passed by the legacy notify autostart).

### Out of Scope
- **Autostart**: deferred to Change 2. Each OS needs its own mechanism (launchd, registry, `.desktop`), and Tauri's autostart plugin covers all three. Building it in the daemon now would be thrown away.
- Hotbar UI, Tauri, packaging, Linux, Codex/OpenCode/Kiro token usage.

## Capabilities

### New Capabilities
- `claude-usage-reader`: per-project token/cost aggregation, time windows, price table
- `project-usage-transport`: `set_project_usage` action and transport gating
- `headless-daemon`: preferences + hook install on headless start
- `hook-command-resolution`: notify/statusline commands that do not depend on the exe location

### Modified Capabilities
- None (only `device-v2-sprites` exists; it is unaffected)

## Approach

- Pure parser + aggregator module. Incremental per-file offsets, refreshed by a dedicated 60 s `_project_usage_checker` via `asyncio.to_thread`; the current snapshot is also sent immediately when a desktop pet connects.
- Project key = git root of `cwd` (fallback `cwd`). Label = basename. One shared function so pets and hotbar compute the same key.
- Cost is labeled "API-equivalent estimate". An unpriced model's share → `cost: null`; totals sum priced shares and carry `cost_partial: true` when any share is unpriced.
- Hook resolution takes the platform, frozen state and notify location as explicit inputs. It keeps today's output for current installs.

## Preservation contract

- TCP: all actions/events, port 19872, v1/v2/v3 negotiation and downgrades. New actions are additive and gated.
- Permission flow `permission_request`/`permission_decision {id, nonce}` stays byte-compatible.
- Hooks: event set, commands, `--uninstall-hooks`, ownership/prune rules. Other tools' hooks are never touched.
- BLE: `ble_client.py`, bleak `<1.0`, GATT UUIDs, firmware, macOS bundle id/TCC.
- Paths: `~/.clawd-tank/`, `~/Library/Logs/ClawdTank`, launchd label. Pets and branding stay unchanged.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Large jsonl history slows the daemon | Med | Incremental offsets; parse off the event loop |
| Price drift / cache pricing | Med | Sourced table with a date; shown as an estimate |
| Hook re-pointing breaks existing installs | Med | Golden tests: unchanged command for current layouts |
| Headless + tray both install hooks | Low | Idempotent install; headless installs only as lock owner; legacy autostart passes `--no-install-hooks` |

## Rollback Plan

Revert the PRs one at a time; each is independent. The action is ignored by Electron (unknown actions fall through in `desktop/main.js`). Hook changes: the existing `--uninstall-hooks` and startup auto-update put the previous commands back.

## Success Criteria

- [ ] Fixture jsonl → exact token totals per project/window; known model cost within 0.01 USD of hand calculation
- [ ] `set_project_usage` reaches only `desktop_pet` transports (test); BLE/sim payloads unchanged
- [ ] Hook command golden tests unchanged for current macOS/Windows layouts; a missing notify exe is re-pointed
- [ ] Headless start applies preferences and installs hooks idempotently
- [ ] Full host suite green (known hanging test deselected)

## Review Workload Forecast

~915 changed lines (reader 390, action 170, hooks 173, headless 182, tests included; reconciled in design.md).
Decision needed before apply: No
Chained PRs recommended: Yes
400-line budget risk: High
Slices: PR1 reader → PR2 action → PR3 hook resolution → PR4 headless (stacked to main).

## Roadmap (separate SDD changes)

- **Change 0**: throwaway Windows Tauri spike, go/no-go (not merged)
- **Change 2**: Tauri shell, sidecar daemon, hotbar, autostart, behind a flag
- **Change 3**: unified packaging, Linux, CI matrix; retire Electron/py2app/Inno

## Proposal question round (auto mode: assumptions for user review)

1. Is cost an API-equivalent estimate from a local table, even for subscription users?
2. Project key = git root (merges monorepo subfolders): is that correct?
3. Are 30d and calendar month both needed?
4. Spike go/no-go on Windows only; macOS validated before Change 2 merges.
5. Electron is kept for one release after Tauri parity.
