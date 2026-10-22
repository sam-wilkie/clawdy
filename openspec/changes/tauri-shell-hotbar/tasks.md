# Tasks: Tauri info hotbar (Change 2)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3,050 total across 11 PRs: 320 / 220 / 270 / 280 / 230 / 250 / 260 / 310 / 240 / 330 / 340 |
| 400-line budget risk | High overall; every PR is under 400 by design (cap 350). PR 1, 10, 11 are split candidates |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> 2 -> ... -> 11, each based on the previous PR branch |
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
| 2 | Pi reader | PR 2 (base PR 1) | `pytest tests/test_pi_usage.py` | Run on real `~/.pi/agent/sessions` | `pi_usage.py` + test |
| 3 | Codex reader | PR 3 (base PR 2) | `pytest tests/test_codex_usage.py` | Run on a real rollout file; verify token inclusion | `codex_usage.py` + test |
| 4 | OpenCode reader | PR 4 (base PR 3) | `pytest tests/test_opencode_usage.py` | Run on real `opencode.db`, confirm dir listing unchanged | `opencode_usage.py` + test |
| 5 | Usage file export | PR 5 (base PR 4) | `pytest tests/test_usage_export.py tests/test_project_usage_transport.py` | Daemon 2 passes, inspect `~/.clawd-tank/project-usage.json` | `usage_export.py`, `daemon.py` hunks |
| 6 | Tauri skeleton + watchdog | PR 6 (base PR 5) | `cargo test` | `cargo run` with `CLAWDY_PARENT_PID` of a killed process: exits | `hotbar/` dir |
| 7 | Bar + usage poll + placement | PR 7 (base PR 6) | `cargo test` | Run hotbar with a sample usage file | `usage.rs`, `placement.rs`, `ui/bar.*` |
| 8 | Panel + UI state | PR 8 (base PR 7) | `node --test` + `cargo test` | Open each agent panel | `state.js`, `panel.*` |
| 9 | State, menu, edit config | PR 9 (base PR 8) | `cargo test` | Drag, collapse, restart, theme | `state.rs`, menu hunks |
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
- [ ] 3.4 REFACTOR; `pytest tests/test_codex_usage.py`; commit `feat(host): add Codex usage reader`.

## PR 4: OpenCode reader (~280) base: PR 3

GitNexus impact: none (new file).

- [ ] 4.1 RED `host/tests/test_opencode_usage.py` (fixture WAL DB built in test): totals per project/window from `message` rows; `part` ignored; row updated between passes re-aggregated; cost reported; live WAL writer still readable, committed rows only; DB bytes unchanged. Spec: opencode Fixture totals, Row updated, Cost reported, Concurrent writer.
- [ ] 4.2 RED same file: cleanly closed WAL DB (no `-wal`/`-shm`) readable and directory listing unchanged; ro failure with `-wal` present -> `error`, never `immutable`; missing table keeps last snapshot with `error`; locked after good pass keeps snapshot; error on first pass; absent. Spec: opencode Locked after a good pass, Missing table, Error on first pass, Absent.
- [ ] 4.3 GREEN `host/clawd_tank_daemon/opencode_usage.py`: `mode=ro` first, `immutable=1` retry only without `-wal`, `timeout=0.5`, 62 d re-aggregation, log once per schema signature. Dep 4.1, 4.2. The RED tests decide whether the immutable retry is reachable (open question 4).
- [ ] 4.4 REFACTOR; `pytest tests/test_opencode_usage.py`; commit `feat(host): add OpenCode usage reader`.

## PR 5: Export + daemon file write (~230) base: PR 4

GitNexus impact first: `ClawdDaemon.__init__`, `_refresh_project_usage`, `_project_usage_checker`, `project_usage_to_payload`.

- [ ] 5.1 RED `host/tests/test_usage_export.py`: four-agent schema keys; absent agent; reader error keeps last good; top 30 by 30d; written on unchanged pass (mtime advances); one reader raising leaves others written; no `.tmp` left; interrupted write leaves old file; `PermissionError` on replace logged, retried next pass. Spec: file all scenarios.
- [ ] 5.2 RED `host/tests/test_project_usage_transport.py`: `set_project_usage` payload keeps same keys and window shape (values may differ per Q3). Spec: file Exclusion rule.
- [ ] 5.3 GREEN `host/clawd_tank_daemon/usage_export.py` (`build_document`, `write_json_atomic`). Dep 5.1.
- [ ] 5.4 GREEN `host/clawd_tank_daemon/daemon.py`: reader list, per-reader `try`, file written every pass, then unchanged Claude-only `set_project_usage`. Dep 5.2, 5.3.
- [ ] 5.5 REFACTOR; `pytest tests/test_usage_export.py tests/test_project_usage_transport.py tests/test_daemon.py` (deselect known hang test); commit `feat(host): export project usage file`.

## PR 6: Tauri skeleton, watchdog, single instance (~250) base: PR 5

GitNexus impact: none (new `hotbar/` dir).

- [ ] 6.1 RED `hotbar/src-tauri/src/pidfile.rs` tests: pidfile `{pid, exe}` round-trip, corrupt file ignored. Spec: process Orphan from a crashed tray.
- [ ] 6.2 RED `watchdog.rs` tests (pure parts): env unset -> no watchdog; invalid PID -> exit now. Spec: window Parent already gone, No parent PID.
- [ ] 6.3 GREEN scaffold `hotbar/src-tauri/{Cargo.toml,build.rs,tauri.conf.json,capabilities/default.json}` (CSP from design, `core:default` + `allow-start-dragging` for `bar`,`panel`), `main.rs`, `pidfile.rs`, `watchdog.rs` (`OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject`, `windows-sys`), single-instance plugin focuses the bar. Spec: window Exit with parent, Single instance. Dep 6.1, 6.2.
- [ ] 6.4 REFACTOR; `cargo test`; `git diff --stat`; commit `feat(hotbar): add Tauri shell skeleton`.

## PR 7: Usage poll, placement, bar (~260) base: PR 6

- [ ] 7.1 RED `placement.rs` tests: `clamp` off-screen, negative coords, partially off-screen, monitor removed or no saved state -> primary right edge, centred, 8 px margin. Spec: window Partially off-screen, Monitor removed.
- [ ] 7.2 RED `usage.rs` test: 5 s mtime poll emits `usage` only on change; malformed file after a good read emits nothing new. Spec: panel Refresh, Missing file.
- [ ] 7.3 GREEN `placement.rs`, `usage.rs`, bar window with four agent cells: `hotbar/ui/bar.html`, `bar.js`, `style.css`. Dep 7.1, 7.2.
- [ ] 7.4 REFACTOR; `cargo test`; commit `feat(hotbar): add bar window with agent cells`.

## PR 8: Panel window and UI state (~310) base: PR 7

- [ ] 8.1 RED `hotbar/ui/state.test.js` (`node --test`): cost format `$X`, `~$X (API-equiv.)`, `no price data` (tokens still shown); today default window; rows sorted by output tokens. Spec: panel Reported, Estimated, Unpriced model.
- [ ] 8.2 RED same file: stale (6 min, default 300 s) shows age; `stale_after_s` 600 not stale; missing file; absent -> "not installed"; error shows kept totals with marker. Spec: panel Stale, Custom threshold, Missing file, Absent agent, Error agent.
- [ ] 8.3 RED same file (added): a malformed or invalid usage payload after a good read keeps the last good data and does not flip to `missing`. Spec: panel requirement "A malformed file after a good read MUST keep the last good data" (spec:54).
- [ ] 8.4 RED Rust `panel_side` tests (left fits, else right, both tight clamp). Spec: panel No room on left, Open panel.
- [ ] 8.5 GREEN `hotbar/ui/package.json` (`"type":"module"`, no deps), `state.js`, `panel.html`, `panel.js`, `panel_side` in `placement.rs`, hide on blur, window switch. Spec: panel Blur, Switch window. Dep 8.1-8.4.
- [ ] 8.6 REFACTOR; `node --test` and `cargo test`; commit `feat(hotbar): add usage panel`.

## PR 9: State, menu, edit config (~240) base: PR 8

- [ ] 9.1 RED `state.rs` tests: save/load `{x,y,collapsed,theme}`, debounced save, corrupt state -> defaults, theme persists. Spec: window Drag and restart, Corrupt state, Theme persists.
- [ ] 9.2 GREEN `state.rs`, collapse to 16 px tab on nearer edge, context menu (Collapse, Theme, Edit config, Reload config), Edit config via opener `open_path` on fixed `hotbar.json` (created if missing). Spec: window Collapse, Menu items. Dep 9.1.
- [ ] 9.3 REFACTOR; `cargo test`; commit `feat(hotbar): persist position and add context menu`.

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

- [ ] F.1 Docs: `CLAUDE.md` (host usage readers, `project-usage.json`, hotbar), `TODO.md` entry, resolve open questions 1 and 4 (Q4 stale default still needs user confirmation).
- [ ] F.2 Manual Windows checklist (record pass/fail in the tracker PR):
  - [ ] Bar appears at default placement; drag, restart, position restored.
  - [ ] Four agent panels (Claude, Codex, OpenCode, Pi) open on the left, or right when no room; blur hides.
  - [ ] Right-click menu: collapse, theme persists, Edit config opens `hotbar.json` in the default editor, Reload config applies.
  - [ ] Hotbar exits when the tray is killed (`taskkill /F /PID <tray>`).
  - [ ] No `msedgewebview2` lingers after that kill without `/T`; if it does, switch `stop()` to `/T` and document it.
  - [ ] Fast tray restart ends with exactly one hotbar; a second manual launch only focuses the bar (single instance).
  - [ ] Custom cells: `open:` browser, `run:` detached, `panel:` output.
- [ ] F.3 macOS and Linux: unverified (L20); not part of this change's acceptance.
