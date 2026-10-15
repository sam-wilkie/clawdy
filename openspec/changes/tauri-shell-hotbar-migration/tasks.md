# Tasks: Shell-agnostic daemon groundwork (Change 1)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~915 total: PR1 390, PR2 170, PR3 173, PR4 182 |
| 400-line budget risk | High overall; PR1 Medium (split to PR1b if >400) |
| Chained PRs recommended | Yes |
| Suggested split | PR1 reader -> (PR1b pricing) -> PR2 transport -> PR3 hooks -> PR4 headless |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Per-slice: PR1 390 (Medium, edge of budget), PR2 170 (Low), PR3 173 (Low), PR4 182 (Low). Chained recommended only for the series; PR2-4 each fit alone.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Pure usage reader | PR 1 (+1b) | `pytest tests/test_claude_usage.py` | Run reader on real `~/.claude/projects`, print snapshot | Delete `claude_usage.py` + its test |
| 2 | `set_project_usage` to pets | PR 2 | `pytest tests/test_project_usage_transport.py` | Daemon + `--sim-only` TCP client with `desktop_pet`, observe line | Revert protocol.py/daemon.py hunks |
| 3 | Hook exe resolution | PR 3 | `pytest tests/test_hook_resolution.py tests/test_hooks_install.py` | `ensure_hooks_current()` against temp HOME | Revert hooks.py/app.py/__main__.py/conftest |
| 4 | Headless parity | PR 4 | `pytest tests/test_headless_startup.py` | `python -m clawd_tank_daemon.daemon` with temp prefs/HOME | Revert daemon.py/preferences.py/notify hunk |

Test cmd prefix: `cd host && .venv/Scripts/python.exe -m pytest` (POSIX: `.venv/bin/pytest`).
Every task: RED test first, GREEN, REFACTOR. Before editing an existing symbol run `gitnexus_impact` (upstream), report HIGH/CRITICAL to the user. Before each commit run `gitnexus_detect_changes`. Conventional commits, no AI attribution.

## PR1: Usage reader (branch off main)

- [x] 1.1 RED `host/tests/test_claude_usage.py`: fixture totals per project/window, dedup `message.id+requestId`, subagent file, monorepo merge, temp cwd, `project_key` (subfolder/relative/nonexistent/`.git` file). Spec: Per-project aggregation. Dep: none.
- [x] 1.2 GREEN create `host/clawd_tank_daemon/claude_usage.py`: `project_key`, `ClaudeUsageReader.refresh/snapshot`, daily buckets, 62-day prune. Dep: 1.1.
- [x] 1.3 RED+GREEN tolerant parsing: garbage line, no `usage`, missing cache_read = 0, dir named `bad.jsonl`, no `projects` dir. Spec: Malformed, No history. Dep: 1.2.
- [x] 1.4 RED+GREEN incremental: partial trailing line deferred, append 2 lines, truncation reset, prune; read-only tree snapshot unchanged. Spec: Append, Read-only. Dep: 1.3.
- [x] 1.5 RED+GREEN time windows: tz UTC-8 boundary `07:59:59Z`/`08:00:00Z`, month reset, bad timestamp skipped. Spec: Day boundary. Dep: 1.2.
- [x] 1.6 PRICES verification: fetch https://docs.anthropic.com/en/docs/about-claude/pricing (fallback anthropic.com/pricing); per row record source URL + as-of date. Must cover Claude 5 ids seen in logs (`claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) and older ids in history (grep local jsonl for distinct `message.model`); no verified price -> unpriced. Dep: none.
- [x] 1.7 RED cost tests: hand-calc within 0.01, 1h tier 2x vs 5m 1.25x, no `cache_creation` -> 5m, unpriced share null + `cost_partial`, all unpriced null, `claude-opus-4-6` unpriced, longest-prefix match. Spec: Known/unknown model, 1-hour tier. Dep: 1.6.
- [x] 1.8 GREEN `PRICES` + cost in `snapshot`. Dep: 1.7.
- [x] 1.9 REFACTOR; measure `git diff --stat`. If >400 lines, move 1.6-1.8 to PR1b (stacked after PR1). Run `gitnexus_detect_changes`, commit `feat(host): add Claude usage reader`. Dep: 1.8.
- [x] 1.10 Docs: CLAUDE.md host section (usage reader module) + TODO.md entry. Dep: 1.9.

## PR2: Transport (base PR1)

- [x] 2.1 `gitnexus_impact` on `ClawdDaemon.__init__`/`run`, `_usage_checker`, `protocol` helpers; report risk. Dep: PR1.
- [x] 2.2 RED `host/tests/test_project_usage_transport.py`: payload shape (30-project cap, sort by 30d, `unpriced`), only `desktop_pet` receives, BLE/sim bytes unchanged, unchanged snapshot not resent, connect sends cached, reader raises -> `set_usage` still sent + logged, interleaved `permission_request` unchanged. Spec: all PR2 scenarios.
- [x] 2.3 GREEN `protocol.project_usage_to_payload` in `host/clawd_tank_daemon/protocol.py`. Dep: 2.2.
- [x] 2.4 GREEN `daemon.py`: `_project_usage_checker` (60 s, `to_thread`, per-pass try/except), `_broadcast_project_usage`, send on pet connect, shutdown cancel. Dep: 2.3.
- [x] 2.5 REFACTOR; confirm `desktop/main.js` ignores unknown action (read-only check). `gitnexus_detect_changes`; commit. Dep: 2.4.
- [x] 2.6 Docs: CLAUDE.md Data Flow (`set_project_usage`, pet-only) + TODO.md. Dep: 2.5.

## PR3: Hook resolution (base PR2)

- [x] 3.1 `gitnexus_impact` on `build_hook_command`, `build_statusline_command`, `HOOK_COMMAND`/`KIRO_HOOK_COMMAND`, codex/antigravity call sites, `app.py`/`__main__.py` callers; report risk. Dep: PR2.
- [x] 3.2 RED `host/tests/test_hook_resolution.py`: goldens notify+statusline (frozen-win, dev-win, pythonw, POSIX), env override drives both, invalid override (relative, missing exe, `"`) ignored + warning. Spec: Golden equality, Explicit location.
- [x] 3.3 RED `ensure_hooks_current`: missing frozen exe leaves settings untouched, old path re-pointed, second run writes nothing, user hooks byte-identical, uninstall unchanged. Spec: Re-point, Up to date, Uninstall.
- [x] 3.4 GREEN `hooks.resolve_hook_executable` + guard + `ensure_hooks_current()` in `host/clawd_tank_menubar/hooks.py`; `conftest.py` `delenv CLAWD_TANK_HOOK_EXE_DIR`. Dep: 3.2, 3.3.
- [x] 3.5 GREEN `app.py:56-61`, `__main__.py:117-122` call the helper. Dep: 3.4.
- [x] 3.6 REFACTOR; `pytest tests/test_hooks_install.py`; `gitnexus_detect_changes`; commit. Dep: 3.5.
- [x] 3.7 Docs: CLAUDE.md (`CLAWD_TANK_HOOK_EXE_DIR`, Windows tray section) + TODO.md. Dep: 3.6.

## PR4: Headless parity (base PR3)

- [x] 4.1 `gitnexus_impact` on `daemon.main`, `ClawdDaemon.__init__`/`run`, `preferences.load_preferences`; report risk. Dep: PR3.
- [x] 4.2 RED `host/tests/test_headless_startup.py`: prefs missing/`{not json`/`[1]` -> defaults, bytes unchanged; `ble_enabled:false`; `sim_enabled` default; `--sim` beats `sim_enabled:false`; `sim_desk_mode` -> `desktop_pet`; `--sim-only --sim-port 12345` unchanged. Spec: Apply preferences.
- [x] 4.3 RED hook startup: `--no-install-hooks` skips, callback only after lock, lost lock no write, corrupt `settings.json` daemon runs, startup exception logged; autostart argv in `host/clawd-tank-notify` has `--no-install-hooks`. Spec: Hook install, Opt-out.
- [x] 4.4 GREEN `preferences.py` `isinstance(stored, dict)` guard; `daemon.main()` prefs/flags + `startup` param; notify autostart flag. Dep: 4.2, 4.3.
- [x] 4.5 REFACTOR; full suite (known hanging test deselected); `gitnexus_detect_changes`; commit. Dep: 4.4.
- [x] 4.6 Docs: CLAUDE.md Host section (headless flags `--no-install-hooks`, prefs mapping) + TODO.md; resolve Open Question (idle SimClient with no prefs). Dep: 4.5.

## Apply status (2026-10-13)

Applied in worktree `O:\Proyectos\Clawdy-hotbar`, branch `feat/hotbar-daemon` (base afcf40c), not pushed:
PR1 `96a9c79` (526 lines, over the 400 budget, PR1b split NOT done), PR2 `8f7a927`, PR3 `11eb877`, PR4 `480f5ec`, verify fixes `c169f2d`.
Full host suite: 1218 passed, 0 failed, with `test_daemon.py::test_ble_connects_and_reconnects_by_itself_after_a_scan_error` deselected (known hang).
Deviations: `gitnexus_impact` / `gitnexus_detect_changes` not run (tool unavailable; callers checked by grep and an independent gentle-ai-verify). `claude-haiku-5-5` left unpriced (price depends on per-request prompt length).
Open question resolved: headless with no prefs runs an idle SimClient (tray parity).
Not verified: real headless daemon run, packaged Windows hook flow.
