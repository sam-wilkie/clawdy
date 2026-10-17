# Tasks: Tauri info hotbar (Change 2)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4,425 authored across 16 PRs (r3): 1-6 = 320 / 220 / 270 / 280 / 230 / 250; 7 = 290; 7a = 350; 7b = 330; 7c = 300; 8 = 320; 8a = 300; 8b = 15 (+ ~1,420 copied pet SVG lines); 9 = 280; 10 = 330; 11 = 340 |
| 400-line budget risk | High overall; every PR is under 400 by design (cap 350). PR 1, 7a, 10, 11 are split candidates; PR 8b is copy-only |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> ... -> 6 -> 7 -> 7a -> 7b -> 7c -> 8 -> 8a -> 8b -> 9 -> 10 -> 11, each based on the previous PR branch |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Branches: tracker `feat/tauri-shell-hotbar` (off `main`, draft/no-merge PR, only it merges to main). PR 1 base = tracker; PR N base = PR N-1 branch. Branch names `feat/tauri-shell-hotbar-prN-<slug>`. A child PR that shows earlier PR changes has a wrong base: retarget before review. Each child PR carries a Chain Context block with a dependency diagram marking the current PR with a pin.

Conventions for every task: strict TDD (RED test first, then GREEN, then REFACTOR). Conventional commits, no AI attribution. Before editing an existing symbol run `gitnexus_impact` (upstream) and report HIGH/CRITICAL; before each commit run `gitnexus_detect_changes`; if GitNexus is unavailable, grep callers and record the deviation. After each PR run `git diff --stat <base>`: if over 400 lines, use the pre-planned split.
Test commands: host `cd host && .venv/Scripts/python.exe -m pytest <paths>`; Rust `. /o/dev/env.sh && cargo test` in `hotbar/src-tauri`; UI `cd hotbar/ui && node --test`.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Shared reader layer + Claude exclusion | PR 1 (base tracker) | `pytest tests/test_usage_common.py tests/test_claude_usage.py` | Run Claude reader on real `~/.claude/projects`, print snapshot | `usage_common.py`, `claude_usage.py`, 2 test files |
| 2 | Pi reader | PR 2 (base PR 1) | `pytest tests/test_pi_usage.py` | Run on real `$PI_CODING_AGENT_DIR/sessions`, else `~/.gentle-shell/agent/sessions` | `pi_usage.py` + test |
| 3 | Codex reader | PR 3 (base PR 2) | `pytest tests/test_codex_usage.py` | Run on a real rollout file; verify token inclusion | `codex_usage.py` + test |
| 4 | OpenCode reader | PR 4 (base PR 3) | `pytest tests/test_opencode_usage.py` | Run on real `opencode.db`, confirm dir listing unchanged | `opencode_usage.py` + test |
| 5 | Usage file export | PR 5 (base PR 4) | `pytest tests/test_usage_export.py tests/test_project_usage_transport.py` | Daemon 2 passes, inspect `~/.clawd-tank/project-usage.json` | `usage_export.py`, `daemon.py` hunks |
| 6 | Tauri skeleton + watchdog | PR 6 (base PR 5) | `cargo test` | `cargo run` with `CLAWDY_PARENT_PID` of a killed process: exits | `hotbar/` dir |
| 7 | Usage poll + placement + placeholder bar | PR 7 (base PR 6) | `cargo test` | Run hotbar with a sample usage file | `usage.rs`, `placement.rs`, `ui/bar.*` |
| 7a | Mochi dock (logos, rings, badges, themes) | PR 7a (base PR 7) | `node --test` | Run hotbar with r2 and r3 sample files, light and dark | `ui/package.json`, `state.js`, `bar.*`, `style.css`, `assets/agents/` |
| 7b | Plan data: Claude, Kiro, export, Gentle Shell path | PR 7b (base PR 7a) | `pytest tests/test_plan_usage.py tests/test_usage_export.py tests/test_pi_usage.py` | Daemon 2 passes, inspect `plan`/`billing` and Gentle Shell totals | `plan_usage.py`, `usage_export.py`, `pi_usage.py`, `daemon.py` hunks |
| 7c | Codex plan via app-server | PR 7c (base PR 7b) | `pytest tests/test_codex_plan.py` | Daemon with real Codex login; confirm no lingering `codex` process | `CodexPlanSource`, `daemon.py` hunk |
| 8 | Panel window + UI state | PR 8 (base PR 7c) | `node --test` + `cargo test` | Open each agent panel and "all agents" | `state.js` panel helpers, `panel.*`, `panel_side` |
| 8a | Panel cards | PR 8a (base PR 8) | `node --test` | Plan, payg, error, absent cards in both themes | `panel.js`, `style.css` panel hunks |
| 8b | Pet assets | PR 8b (base PR 8a) | `node --test` | Pets animate in each card | `assets/pets/`, card `<img>` |
| 9 | State, collapsed pill, menu, edit config | PR 9 (base PR 8b) | `cargo test` + `node --test` | Drag, collapse, restart, theme, gear | `state.rs`, collapsed pill, menu hunks |
| 10 | Custom cells | PR 10 (base PR 9) | `cargo test` + `node --test` | Click open/run/panel cells | `config.rs`, `actions.rs`, UI cells |
| 11 | Tray integration | PR 11 (base PR 10) | `pytest tests/test_hotbar_process.py tests/test_controller*.py` | Tray start/quit, kill, toggle | `hotbar_process.py`, controller/prefs/views hunks |

## PR 1: usage_common + Claude refactor (~320, split candidate) base: tracker

GitNexus impact first: `project_key`, `ClaudeUsageReader` (`refresh`, `_read_file`, `_ingest`, `_prune`, `snapshot`), `_apply_cost`, `_price`, `PRICES`.

- [x] 1.1 RED `host/tests/test_usage_common.py`: git repo under injected `temp_root` -> None, same repo outside -> key; no `temp_root` + repo under `tmp_path` -> None (gettempdir default); non-git and relative -> None; `.git` file -> key. Spec: claude Excluded sessions, file Exclusion rule.
- [x] 1.2 RED same file: tail reader (partial line deferred, truncation reset, per-file context kept), buckets windows in fixed tz, longest-prefix price. Spec: claude Fixture totals, Monorepo subfolders.
- [x] 1.3 GREEN `host/clawd_tank_daemon/usage_common.py`: `project_key(cwd, temp_root)`, `price_lookup`, `JsonlTailReader`, `UsageBuckets`. Dep 1.1, 1.2.
- [x] 1.4 RED update `host/tests/test_claude_usage.py`: `reader()` and direct `project_key` calls pass fake `temp_root`; change expectations of `test_project_key_non_git_falls_back_to_cwd` (:72, None), `test_project_key_nonexistent_and_relative_used_verbatim` (:76, None), `test_monorepo_merges_and_temp_dir_is_own_project` (:98, `scratch` excluded). Spec: claude Excluded sessions.
- [x] 1.5 GREEN `host/clawd_tank_daemon/claude_usage.py`: `ClaudeUsageReader` subclasses the common layer, drops None rows. Dep 1.3, 1.4.
- [x] 1.6 REFACTOR; run full `tests/test_claude_usage.py`; `git diff --stat`; commit `refactor(host): extract shared usage reader layer`.
- Split point if over 400: PR 1a = tasks 1.1-1.3 (`usage_common` + its test); PR 1b = 1.4-1.6 (Claude refactor + edited tests), based on 1a. PR 2 then bases on 1b.

## PR 2: Pi reader (~220) base: PR 1

GitNexus impact: none (new file); reuse `usage_common` only.

- [x] 2.1 RED `host/tests/test_pi_usage.py` + fixtures: exact totals per project/window; cwd from `session` record; missing `cost` -> `cost_partial`; duplicate entry `id` counted once; garbage/truncated lines skipped; absent root -> `absent`. Spec: pi Fixture totals, Missing cost, Duplicate entry id, Garbage and truncated lines, Absent.
- [x] 2.2 GREEN `host/clawd_tank_daemon/pi_usage.py` (reported cost summed, `temp_root` seam). Dep 2.1.
- [x] 2.3 REFACTOR; verify with `pytest tests/test_pi_usage.py`; commit `feat(host): add Pi usage reader`.

## PR 3: Codex reader (~270) base: PR 2

GitNexus impact: none (new file).

- [x] 3.1 Verify Codex token inclusion on a real `~/.codex/sessions` rollout (`input_tokens` includes cached/cache-write?); record result in the test fixture comment. Closes open question 1.
- [x] 3.2 RED `host/tests/test_codex_usage.py` + fixtures: `token_count` ignored (no double counting); duplicate `response_id` once; model from latest `turn_context`; cwd from `session_meta`; excluded cwd; priced vs unpriced -> `cost: null`; garbage line; absent; append keeps per-file context. Spec: codex all scenarios.
- [x] 3.3 GREEN `host/clawd_tank_daemon/codex_usage.py` with `CODEX_PRICES` (dated source per row; unverified -> unpriced). Dep 3.1, 3.2.
- [x] 3.4 REFACTOR; `pytest tests/test_codex_usage.py`; commit `feat(host): add Codex usage reader`.

## PR 4: OpenCode reader (~280) base: PR 3

GitNexus impact: none (new file).

- [x] 4.1 RED `host/tests/test_opencode_usage.py` (fixture WAL DB built in test): totals per project/window from `message` rows; `part` ignored; row updated between passes re-aggregated; cost reported; live WAL writer still readable, committed rows only; DB bytes unchanged. Spec: opencode Fixture totals, Row updated, Cost reported, Concurrent writer.
- [x] 4.2 RED same file: cleanly closed WAL DB (no `-wal`/`-shm`) readable and directory listing unchanged; ro failure with `-wal` present -> `error`, never `immutable`; missing table keeps last snapshot with `error`; locked after good pass keeps snapshot; error on first pass; absent. Spec: opencode Locked after a good pass, Missing table, Error on first pass, Absent.
- [x] 4.3 GREEN `host/clawd_tank_daemon/opencode_usage.py`: `mode=ro` first, `immutable=1` retry only without `-wal`, `timeout=0.5`, 62 d re-aggregation, log once per schema signature. Dep 4.1, 4.2. The RED tests decide whether the immutable retry is reachable (open question 4).
- [x] 4.4 REFACTOR; `pytest tests/test_opencode_usage.py`; commit `feat(host): add OpenCode usage reader`.

## PR 5: Export + daemon file write (~230) base: PR 4

GitNexus impact first: `ClawdDaemon.__init__`, `_refresh_project_usage`, `_project_usage_checker`, `project_usage_to_payload`.

- [x] 5.1 RED `host/tests/test_usage_export.py`: four-agent schema keys; absent agent; reader error keeps last good; top 30 by 30d; written on unchanged pass (mtime advances); one reader raising leaves others written; no `.tmp` left; interrupted write leaves old file; `PermissionError` on replace logged, retried next pass. Spec: file all scenarios.
- [x] 5.2 RED `host/tests/test_project_usage_transport.py`: `set_project_usage` payload keeps same keys and window shape (values may differ per Q3). Spec: file Exclusion rule.
- [x] 5.3 GREEN `host/clawd_tank_daemon/usage_export.py` (`build_document`, `write_json_atomic`). Dep 5.1.
- [x] 5.4 GREEN `host/clawd_tank_daemon/daemon.py`: reader list, per-reader `try`, file written every pass, then unchanged Claude-only `set_project_usage`. Dep 5.2, 5.3.
- [x] 5.5 REFACTOR; `pytest tests/test_usage_export.py tests/test_project_usage_transport.py tests/test_daemon.py` (deselect known hang test); commit `feat(host): export project usage file`.

## PR 6: Tauri skeleton, watchdog, single instance (~250) base: PR 5

GitNexus impact: none (new `hotbar/` dir).

- [x] 6.1 RED `hotbar/src-tauri/src/pidfile.rs` tests: pidfile `{pid, exe}` round-trip, corrupt file ignored. Spec: process Orphan from a crashed tray.
- [x] 6.2 RED `watchdog.rs` tests (pure parts): env unset -> no watchdog; invalid PID -> exit now. Spec: window Parent already gone, No parent PID.
- [x] 6.3 GREEN scaffold `hotbar/src-tauri/{Cargo.toml,build.rs,tauri.conf.json,capabilities/default.json}` (CSP from design, `core:default` + `allow-start-dragging` for `bar`,`panel`), `main.rs`, `pidfile.rs`, `watchdog.rs` (`OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject`, `windows-sys`), single-instance plugin focuses the bar. Spec: window Exit with parent, Single instance. Dep 6.1, 6.2.
- [x] 6.4 REFACTOR; `cargo test`; `git diff --stat`; commit `feat(hotbar): add Tauri shell skeleton`.

## PR 7: Usage poll, placement, placeholder bar (~290) base: PR 6

r3: the dock rewrite moved to PR 7a; PR 7 ships the Rust poll and placement with the existing placeholder bar as its run harness. `usage.rs valid_document` must stay unchanged (requires only the four r2 agents, ignores `plan`/`billing`/`kiro`).

- [x] 7.1 RED `placement.rs` tests: `clamp` off-screen, negative coords, partially off-screen, monitor removed or no saved state -> primary right edge, centred, 8 px margin. Spec: window Partially off-screen, Monitor removed.
- [x] 7.2 RED `usage.rs` test: 5 s mtime poll emits `usage` only on change; malformed file after a good read emits nothing new. Spec: panel Refresh, Missing file.
- [x] 7.3 GREEN `placement.rs`, `usage.rs`, bar window with four agent cells: `hotbar/ui/bar.html`, `bar.js`, `style.css`. Dep 7.1, 7.2.
- [x] 7.4 RED/GREEN `usage.rs` test: an r3 document with `billing`, `plan` and a `kiro` entry validates unchanged; a document missing `kiro` still validates. Spec: file Older consumer, panel Agent missing from file.
- [ ] 7.5 REFACTOR; `cargo test`; leave `hotbar/ui/assets/` untracked for PR 7a; commit `feat(hotbar): add usage poll, placement and bar window`.

## PR 7a: Mochi dock (~350, split candidate) base: PR 7

GitNexus impact: none on host code; the bar UI files are rewritten. GitNexus unavailable during implementation; `rg` checked bar render callers, stylesheet references and usage IPC wiring instead (no host or Rust symbols changed).

- [x] 7a.1 RED `hotbar/ui/state.test.js` (`node --test`, `hotbar/ui/package.json` `"type":"module"`, no deps): agent list order and display names (`pi` -> "Gentle Shell", Kiro present); `billingOf` (`plan`/`payg`, absent `billing` -> `payg`); `ringOf` = max `used_pct`, cherry at >= 90, `null` when `plan` absent, not `ok`, or malformed (`limits` not a list, non-numeric pct); agent missing from file -> `absent`. Spec: panel Gentle Shell label, Old file without billing, Ring at warning level, Ring in brand colour, Malformed plan, Agent missing from file.
- [x] 7a.2 RED same file: dock labels in Spanish: plan agent lists each limit with `%`; payg agent shows today's cost (`≈` + "estimado" when estimated); `error` adds "falló la lectura"; es-CO USD formatting. Spec: panel Payg badge, Reported, Estimated.
- [x] 7a.3 GREEN `hotbar/ui/state.js` (dock helpers). Dep 7a.1, 7a.2.
- [x] 7a.4 GREEN `bar.html`, `bar.js` (ES module, renders from `usage` event and `usage_snapshot`), `style.css`: Mochi tokens light and dark (values in design r3), `prefers-color-scheme` default, vertical pill dock (chevron, agent buttons, "all agents", gear), monochrome logos (`currentColor` SVGs, `gentle-shell-mask.png` CSS mask), rings in brand colour, "$" badge, cherry error badge, stale badge on "all agents", `aria-label`/`title` per button. Chevron and gear render but are wired in PR 9; agent buttons emit the panel request wired in PR 8. Dep 7a.3.
- [ ] 7a.5 REFACTOR; `node --test`; manual run with an r2 file (all payg, no rings) and an r3 sample (rings, cherry at 93 %), both themes; commit `feat(hotbar): add plan-first agent dock`.
- Split point if over 400: PR 7a-1 = 7a.1-7a.3 (`state.js` + tests + `package.json`); PR 7a-2 = 7a.4-7a.5 (rendering, CSS, assets), based on 7a-1.

## PR 7b: Plan usage (Claude, Kiro) + Kiro entry + Gentle Shell path (~330) base: PR 7a

GitNexus impact first: `build_document`, `PiUsageReader.__init__`, `ClawdDaemon.__init__`, `_refresh_project_usage`. `read_usage_from_cache` is read for reference, not changed.

- [x] 7b.1 RED `host/tests/test_pi_usage.py` (added): `pi_sessions_root` returns `$PI_CODING_AGENT_DIR/sessions` when set, else `~/.gentle-shell/agent/sessions` (injected `env`/`home`); empty env var ignored; a daemon wiring test asserts the Pi reader root is `pi_sessions_root()` and never `~/.pi`. Spec: pi Default root, Environment override, Legacy directory ignored.
- [x] 7b.2 GREEN `pi_usage.pi_sessions_root` and `daemon.py:458` uses it. Dep 7b.1.
- [x] 7b.3 RED `host/tests/test_plan_usage.py`: Claude both limits with ISO `resets_at`, only weekly, no cache -> `no_data`, negative/non-numeric pct omitted. Spec: plan Both limits, Only weekly, No cache.
- [x] 7b.4 RED same file, Kiro (DB built in the test with `sqlite3`): CREDIT 340/1000 -> `credits` and 34 %; newest `timestamp` across default and profile DB wins; a secret-storage row is never selected and DB bytes plus directory listing are unchanged; no DB -> `absent`; over 64 MiB skipped; malformed JSON value skipped; `CLAWDY_KIRO_STATE_DB` override. Spec: plan Credit cache, Newest profile wins, Other keys never read, No Kiro install.
- [x] 7b.5 GREEN `host/clawd_tank_daemon/plan_usage.py`: `read_claude_plan`, `read_kiro_plan` (OpenCode ro open rule, two-key query only). Dep 7b.3, 7b.4.
- [x] 7b.6 RED `host/tests/test_usage_export.py` (added): `billing` on every non-absent entry (Claude/Kiro `plan`, OpenCode/Pi `payg`, Codex `plan` by default); Kiro entry with `cost_kind` `none` and no `totals`/`projects`; a raising plan source keeps token blocks and status, keeps the last good `plan` with `plan.status` `error`; Kiro raising after a good pass -> `status` `error` with last plan; `version` stays 1. Spec: file Five agents, Kiro entry has no token data, Kiro absent, Claude limits, Plan source raises; plan Isolation.
- [x] 7b.7 GREEN `usage_export.build_document(readers, now, previous, plans=None)` and `daemon.py` plan sources in `to_thread`, each in its own `try`. Dep 7b.5, 7b.6.
- [ ] 7b.8 REFACTOR; `pytest tests/test_plan_usage.py tests/test_usage_export.py tests/test_pi_usage.py tests/test_project_usage_transport.py`; run the daemon twice and inspect the file; commit `feat(host): add plan usage and Kiro to the usage file` (the path fix may go first as `fix(host): read Gentle Shell sessions from its agent dir`).

## PR 7c: Codex plan via app-server (~300) base: PR 7b

GitNexus impact first: `_refresh_project_usage`, `build_document` (plans input only). Threat matrix row "Process integration: Codex app-server" applies; every RED below is required.

- [x] 7c.1 RED `host/tests/test_codex_plan.py` exe lookup: `CLAWDY_CODEX_BIN` existing file wins, missing file -> `not_installed`; `PATH` native exe; `.cmd`/`.bat` rejected; `CODEX_HOME` releases, `%LOCALAPPDATA%` and npm vendor candidates (injected env/home/fs). Spec: plan Script shim rejected.
- [x] 7c.2 RED same file with a fake popen speaking JSON-RPC lines: exact argv `[exe, "app-server", "--listen", "stdio://"]`, no shell, stderr discarded, no-window flag on Windows; `chatgpt` account -> `primary`/`weekly` with `window_min` and `reset_credits`; `apiKey` -> `payg`, rate limits not requested; no account -> `signed_out`; JSON-RPC error and malformed lines -> `error`; server request answered `-32601`; never sends a consume method. Spec: plan ChatGPT account, API key account, Server request refused.
- [x] 7c.3 RED same file: 15 s timeout kills the child and keeps the previous `billing`; child stdin closed and reaped on every path; second refresh inside 300 s spawns nothing; `billing` before the first success is `plan`. Spec: plan Timeout, Within cadence.
- [x] 7c.4 GREEN `CodexPlanSource` in `plan_usage.py`, daemon wiring (off-thread, 300 s). Dep 7c.1-7c.3.
- [ ] 7c.5 REFACTOR; `pytest tests/test_codex_plan.py tests/test_usage_export.py`; manual: real Codex login gives limits and no `codex` process remains after the pass; commit `feat(host): read Codex plan limits from the app-server`.

## PR 8: Panel window and UI state (~320) base: PR 7c

GitNexus unavailable during implementation; `rg` checked placement, usage event/snapshot and dock request callers instead. No HIGH/CRITICAL impact result available.

- [x] 8.1 RED `hotbar/ui/state.test.js` (panel helpers): money only for `payg` (plan agent with a cost shows none and is excluded from the header spend); reported es-CO USD, estimated `≈` + "estimado", `null` -> "Sin precio" (tokens still shown); header spend summed over payg agents with `≈` when any is estimated; today default window; rows sorted by output tokens. Spec: panel Reported, Estimated, Unpriced model, Plan agent cost hidden.
- [x] 8.2 RED same file: stale (6 min, default 300 s) shows age; `stale_after_s` 600 not stale; missing file; absent -> "No instalado"; error shows kept totals with marker. Spec: panel Stale, Custom threshold, Missing file, Absent agent, Error agent.
- [x] 8.3 RED same file: a malformed or invalid usage payload after a good read keeps the last good data and does not flip to `missing`. Spec: panel requirement "A malformed file after a good read MUST keep the last good data".
- [x] 8.4 RED Rust `panel_side` tests (left fits, else right, both tight clamp). Spec: panel No room on left, Open panel.
- [x] 8.5 GREEN `state.js` panel helpers, `panel.html`, `panel.js` shell (window segment Hoy/7 días/30 días/Mes, header spend and freshness, close), `panel_side` in `placement.rs`, hide on blur, focus by agent button or "all agents". Spec: panel Open panel, All agents, Blur, Switch window, Refresh. Dep 8.1-8.4.
- [ ] 8.6 REFACTOR; `node --test` and `cargo test`; commit `feat(hotbar): add usage panel`.

## PR 8a: Panel agent cards (~300) base: PR 8

- [x] 8a.1 RED `state.test.js`: limit names by `id` in Spanish with `label` fallback, `window_min` shown when present; reset time text from `resets_at` (and none when `null`); Kiro credits used/plan/remaining (es-CO grouping); Codex `reset_credits` note only when numeric; billing chip text ("Plan", "Pago por uso", "API · estimado"); plan agent without `ok` plan -> no-limits note; project share = tokens / max. Spec: panel Claude on a plan, Kiro credits, Plan without data, Codex card.
- [x] 8a.2 GREEN `panel.js` cards and `style.css` panel hunks: coloured logo beside the name, chips (10 px 700 uppercase), plan bars in brand colour (cherry at >= 90), token grid, project rows with brand share bars and "ver todos" toggle, payg cost per project, error and stale notes. Dep 8a.1.
- [ ] 8a.3 REFACTOR; `node --test`; manual check of plan, payg, error and absent cards in both themes; commit `feat(hotbar): add plan-first agent cards`.
  - Progress: committed (133cd25, 1ed7f8e); dark theme checked on the real bar; light theme still unchecked. Follow-up fixes 00485eb, b071aed: second click on the same icon closes the panel, gap to the dock tightened.

## PR 8b: Pet assets (~15 authored, ~1,420 copied) base: PR 8a

- [x] 8b.1 Copy `desktop/renderer/assets/clawd-idle-living-v2.svg`, `codex/cloud-idle-v2.svg`, `monster/monster-idle-v2.svg` into `hotbar/ui/assets/pets/` (`claude-idle.svg`, `codex-idle.svg`, `monster-idle.svg`) and crop only the `viewBox` to the sprite bounds; record in the PR body that `git diff --no-index` against the source shows only the `viewBox` line.
- [x] 8b.2 RED `state.test.js`: pet per agent (Claude crab, Codex cloud, Kiro/OpenCode/Gentle Shell monster). GREEN card `<img alt="">` using it; CSP unchanged (`img-src 'self'`). Spec: panel Agent cards.
- [x] 8b.3 Manual: pets animate in WebView2 and stay within the card; commit `feat(hotbar): add agent pets to panel cards`.
  - Progress: committed (bf49caa). Checked in a real Electron (Chromium) render and confirmed by the user in the real app (WebView2): pets display inside the card and animate. `render()` now skips replacing identical cards so the 5 s refresh no longer restarts the animation.

## PR 9: State, collapsed pill, menu, edit config (~280) base: PR 8b

- [ ] 9.1 RED `state.rs` tests: save/load `{x,y,collapsed,theme}`, debounced save, corrupt state -> defaults, theme persists. Spec: window Drag and restart, Corrupt state, Theme persists.
- [ ] 9.2 RED `state.test.js`: collapsed dot class per agent (brand; dim < 30; alert >= 90 or `error`; track when `absent`; payg in brand) and the attention list naming agents at >= 90 % or `error`. Spec: panel Attention tooltip, Absent dot.
- [ ] 9.3 GREEN `state.rs`; collapsed pill (chevron + dots, tooltip and `aria-label` with attention names) with the window resized to the pill and anchored to the nearer edge; chevron toggles; context menu (Collapse, Theme, Edit config, Reload config) also opened by the gear button; Edit config via opener `open_path` on fixed `hotbar.json` (created if missing). Spec: window Collapse, Menu items. Dep 9.1, 9.2.
- [ ] 9.4 REFACTOR; `cargo test`, `node --test`; commit `feat(hotbar): persist position, collapse and add context menu`.

## PR 10: Custom cells (~330, split candidate) base: PR 9

- [ ] 10.1 RED `config.rs` tests: missing config -> default created; invalid cell disabled with error; malformed JSON on reload keeps last good + error badge; unknown prefix, `open:file://`, `javascript:`, empty program rejected at load. Spec: cells Missing config, Invalid cell, Malformed JSON on reload, Rejected scheme.
- [ ] 10.2 RED `actions.rs` tests: invoking an unknown cell id runs nothing and returns an error (spec:117). Invoking a cell whose `open:` is non-http(s) is rejected at invoke time without opening, even if config was bypassed (spec:123). Spec: cells Unknown id, Rejected scheme; Threat matrix.
- [ ] 10.3 RED `actions.rs` tests: `run:` argv asserted, metacharacters literal, null stdio, detached; `panel:` timeout kills child at 10 s, output capped 64 KiB, non-zero exit reported. Spec: cells Allowed, No shell, Detached, Empty program, Timeout, Output cap, Non-zero exit.
- [ ] 10.4 GREEN `config.rs`, `actions.rs` (`run_cell(id)`, id lookup in loaded config, opener `open_url` http/https only), UI custom cells in `bar.js`. Dep 10.1-10.3.
- [ ] 10.5 REFACTOR; `cargo test`, `node --test`; commit `feat(hotbar): add custom cells`.
- Split point if over 400: PR 10a = 10.1 + `config.rs` (parsing, rejection at load); PR 10b = 10.2-10.4 `actions.rs` + UI cells, based on 10a. PR 11 then bases on 10b.

## PR 11: Tray integration (~340, split candidate) base: PR 10

GitNexus impact first: `ClawdTankController` (`__init__`, `start`, `quit`, `_render`, `_shutdown_sequence`, `_kill_sim_now`), `TrayState`, `WindowsTrayView` menu build, `RumpsTrayView.build/render`, `preferences.DEFAULTS`.

- [ ] 11.1 RED `host/tests/test_hotbar_process.py` (fake popen): exe lookup order (`CLAWDY_HOTBAR_EXE`, next to `sys.executable`, repo release); missing exe logs warning, no crash; stale kill only on image-path match, mismatch or dead pid never kills; `CLAWDY_PARENT_PID` passed; `stop()` twice safe; `taskkill /F /PID` without `/T`. Spec: process Normal lifecycle, Stop twice, Orphan, Reused pid, Env override, No exe.
- [ ] 11.2 GREEN `host/clawd_tank_daemon/hotbar_process.py` (`HotbarProcess`, pidfile, `QueryFullProcessImageNameW`, log to `hotbar.log`). Dep 11.1.
- [ ] 11.3 RED controller tests (fake factory): starts with `controller.start` when enabled; `quit` stops it incl. force-exit path; toggle persists `hotbar_enabled` and starts/stops; disabled at startup does not spawn. Spec: process Toggle off, Disabled at startup.
- [ ] 11.4 RED headless test: `daemon._build_daemon`/`main` with prefs `hotbar_enabled:true` never constructs/starts `HotbarProcess` (patched to raise). Spec: process Headless start.
- [ ] 11.5 GREEN `controller.py` (factory, start/quit/toggle), `preferences.py` (`hotbar_enabled: True`), `TrayState.hotbar_enabled`, `windows_tray.py`, `rumps_view.py` menu item. Dep 11.2-11.4.
- [ ] 11.6 REFACTOR; run `pytest tests/test_hotbar_process.py` plus controller and tray tests; commit `feat(host): start hotbar from the tray`.
- Split point if over 400: PR 11a = 11.1-11.2 (`hotbar_process.py` + test); PR 11b = 11.3-11.6 (controller, preferences, views, headless test), based on 11a.

## Final: Docs and manual Windows checklist (after PR 11, on the tracker)

- [ ] F.1 Docs: `CLAUDE.md` (host usage readers, plan sources, `project-usage.json` with `billing`/`plan`, hotbar), `TODO.md` entry, r3 open questions on Claude and Codex billing defaults, resolve open questions 1 and 4 (Q4 stale default still needs user confirmation).
- [ ] F.2 Manual Windows checklist (record pass/fail in the tracker PR):
  - [ ] Bar appears at default placement; drag, restart, position restored.
  - [ ] Five agent buttons (Claude, Codex, OpenCode, Kiro, Gentle Shell) open their cards on the left, or right when no room; "all agents" shows every card; blur hides.
  - [ ] Plan agents show limits and no money; rings match the highest limit; OpenCode and Gentle Shell show "$" and reported cost; Codex on an API key shows estimated cost.
  - [ ] Collapsed pill dots and attention tooltip; light and dark themes match the mockup.
  - [ ] Gentle Shell totals reflect current `~/.gentle-shell/agent/sessions` data.
  - [ ] Right-click menu: collapse, theme persists, Edit config opens `hotbar.json` in the default editor, Reload config applies.
  - [ ] Hotbar exits when the tray is killed (`taskkill /F /PID <tray>`).
  - [ ] No `msedgewebview2` lingers after that kill without `/T`; if it does, switch `stop()` to `/T` and document it.
  - [ ] Fast tray restart ends with exactly one hotbar; a second manual launch only focuses the bar (single instance).
  - [ ] Custom cells: `open:` browser, `run:` detached, `panel:` output.
- [ ] F.3 macOS and Linux: unverified (L20); not part of this change's acceptance.
