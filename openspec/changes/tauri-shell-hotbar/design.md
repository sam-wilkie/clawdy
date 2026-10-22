# Design: Tauri info hotbar (Change 2)

## Technical Approach

The daemon reads usage for four agents, the Tauri hotbar shows it, and the tray owns the hotbar's lifetime. The daemon writes one file, `~/.clawd-tank/project-usage.json`, and the hotbar polls it. There is no new port or transport. Python keeps all parsing and prices. Rust handles the window, placement, config and actions. The UI is vanilla HTML/JS with `withGlobalTauri` and no node dependencies.

    ~/.claude/projects  ~/.codex/sessions  opencode.db (ro)  ~/.pi/agent/sessions
            └──────────────┴── readers (usage_common) ──┴──────────┘
                                   │ daemon, every 60 s, to_thread
                                   ▼
                  ~/.clawd-tank/project-usage.json (atomic, always rewritten)
                                   │ mtime poll 5 s
    tray ──spawn/kill──► clawdy-hotbar.exe ──event "usage"──► bar.html / panel.html
         CLAWDY_PARENT_PID      ▲ hotbar.json (user) / hotbar-state.json (hotbar)

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Shared reader layer | New `usage_common.py`: `project_key`, `price_lookup` (longest prefix), `JsonlTailReader` (offsets, partial lines, retention, prune, per-file context), `UsageBuckets` (`(key, day, model) -> [in, out, cw5, cw1, cr, reported_cost, unreported_n]` + `snapshot(now)`). `ClaudeUsageReader` becomes a subclass. | Copy the Claude reader 3x | Same windows and project key by construction; Change 1 tests guard the refactor |
| Exclusion (Q3) | `project_key(cwd, temp_root=None) -> str \| None`. It returns None if cwd is relative, has no `.git` ancestor, or resolves under `temp_root` (normcase + realpath; None means `tempfile.gettempdir()`). The cache key is `(cwd, temp_root)`. Readers drop None rows. | Filter at export only | One rule, so `set_project_usage` and the file never diverge |
| Temp-root test seam | Every reader takes `temp_root: str \| None = None` and passes it to `project_key`. Tests pass `tmp_path / "fake-tmp"` (empty, not an ancestor of the fixture repos), because pytest's `tmp_path` sits under the OS temp dir and would otherwise exclude every fixture. Production passes nothing. | conftest monkeypatching `tempfile.tempdir` | An explicit parameter beats global state; one test still checks the real default |
| Codex source | Only `token_usage_record` lines, deduped on `response_id`. `in = input_tokens - cached_input_tokens - cache_write_input_tokens`, `cr = cached`, `cw5 = cache_write`, `out = output_tokens` (reasoning is already inside it). The model comes from the latest `turn_context`/`thread_settings_applied` in the file, the cwd from `session_meta`. | `event_msg token_count` | Cumulative counts lead to double counting. The inclusion arithmetic must be checked against a real file at apply time |
| Codex prices | `CODEX_PRICES` holds only rows with a dated source. Unverified models are unpriced, which shows `no price data`. | Guessed prices | Proposal risk |
| Pi | The cwd comes from the file's `session` record. Assistant `usage` maps `input/output/cacheRead/cacheWrite`. `cost.total` is summed as reported cost. Messages are deduped on the entry `id` when present. | — | Verified format |
| OpenCode source | Legacy `message` table. Assistant rows with `time_created >= now - 62 d` are re-aggregated fully on each pass. The project comes from `data.path.cwd` through `project_key`. Uses `data.cost` and `tokens{input,output,cache{read,write}}`; `part` is never read. | `session_v2`/`session_message` (not inspected); `part` step-finish (double count); incremental by `time_created` (rows are updated in place at completion) | Verified fields. A full pass over 62 d is cheap off-thread |
| OpenCode open (WAL) | `file:...?mode=ro` first. A read-only connection never creates `-wal`/`-shm`, and while OpenCode runs it reads a consistent snapshot through OpenCode's own `-shm`. If that open or the first query fails with `CANTOPEN`/`READONLY` (no `-shm`, typical after OpenCode closed cleanly), retry once with `immutable=1`, but only when no `-wal` file exists, which means no writer has uncommitted pages. With a `-wal` present and a ro failure the reader reports `error`. | `immutable=1` always (can read stale or torn data while OpenCode writes); read-write open (creates files, can block OpenCode) | Never writes beside the DB and never reads half-applied WAL |
| OpenCode failure | `sqlite3.connect(uri, uri=True, timeout=0.5)`. A missing table/column or `OperationalError` keeps the previous buckets, sets `status:"error"` and logs once per schema signature. | Raise | Locked or migrating DB |
| Export | `usage_export.build_document(readers, now)` + `write_json_atomic(path, obj)` (mkstemp in same dir + `os.replace`). `_refresh_project_usage` refreshes each reader in its own `try`, writes the file every pass, then keeps today's Claude-only `set_project_usage` unchanged. | Reuse `session_store.save_sessions` | Its writer is inlined, not a helper; extracting it is an unrelated refactor (about 12 duplicated lines) |
| Windows replace | Rust reads with `std::fs::read`, whose default share mode includes `FILE_SHARE_DELETE`. On Python `PermissionError` the writer logs and retries on the next pass. | Lock file | Never blocks the daemon |
| Config vs state | `~/.clawd-tank/hotbar.json` is user-owned and only read; a default is created if missing. `~/.clawd-tank/hotbar-state.json` is hotbar-owned and stores `{x, y, collapsed, theme}`, saved debounced on move end and on toggle. | One file; Tauri `app_config_dir` | The hotbar never rewrites a hand-edited file, and one data dir follows the project convention |
| Actions | The UI invokes `run_cell(id)`. Rust looks the action up in the loaded config. `open:` goes through `tauri-plugin-opener` `open_url`, http/https only. `run:` uses `Command::new(prog).args(args)` with null stdio and `DETACHED_PROCESS`. `panel:` runs in a thread with a 10 s timeout (then kill), stdout capped at 64 KiB, UTF-8 lossy. | JS sends the command line | Script injection in the webview cannot name a program |
| Parent watchdog | Windows: `OpenProcess(SYNCHRONIZE)` on `CLAWDY_PARENT_PID` at startup, then `WaitForSingleObject(INFINITE)` in a thread, then `app.exit(0)`. If OpenProcess fails the hotbar exits immediately. Unix: poll `std::os::unix::process::parent_id()` every 2 s. The env var unset means dev mode with no watchdog. Uses the `windows-sys` crate. | PID polling on Windows | A handle survives PID reuse, and there is no polling |
| Single instance | `tauri-plugin-single-instance`: a second launch shows and focuses the bar. | Named mutex | Official plugin |
| Process kill | Tray `stop()` runs `taskkill /F /PID <pid>` without `/T`. | `/T` tree kill (proposal) | `/T` would also kill programs started by `run:`. WebView2 exits with its host process; the manual check confirms it, and if it does not, switch to `/T` and document it |
| Stale cleanup | The hotbar writes `~/.clawd-tank/hotbar.pid` `{pid, exe}`. Before spawning, `HotbarProcess.start()` kills the recorded pid only if the live image path (ctypes `QueryFullProcessImageNameW`) equals both the recorded `exe` and the resolved exe. Skipped off Windows. | `taskkill /IM` (as for the sims) | Limits cleanup to our install path and survives PID reuse. This also covers a fast tray restart, where the orphan is still alive and single-instance would swallow the new launch |
| Process manager | New synchronous `host/clawd_tank_daemon/hotbar_process.py` (`subprocess.Popen`, stderr appended to `~/.clawd-tank/hotbar.log`). It shares no code with `SimProcessManager`. | Subclass or extract from `SimProcessManager` | The sim manager is asyncio plus TCP. The only overlap is about 5 lines of `taskkill`; extracting it would touch stable code |
| Exe lookup | `CLAWDY_HOTBAR_EXE` (absolute existing file), then `clawdy-hotbar(.exe)` next to `sys.executable`, then repo `hotbar/src-tauri/target/release/`. None logs a warning and is skipped. | PATH | Matches the proposal |
| Panel | A second hidden window, `panel`. Pure `panel_side(bar, size, work_area)` puts it on the left if it fits, else the right, aligned with the bar's top and clamped. It hides on blur. | Resizing one window | The bar never moves |
| Placement | Pure `clamp(rect, work_areas, primary)`: if a monitor contains the saved rect's centre, clamp the rect into that monitor's work area. Otherwise (monitor removed, no saved state, rect fully off-screen) use the default placement: right edge of the primary work area, vertically centred, 8 px margin. Collapsing shrinks the bar to a 16 px tab on the nearer edge. | — | Unit-testable |
| Staleness (Q4) | `stale_after_s` in config, default 300. UI states: `missing` (no file or invalid on first read), `stale` (`now - generated_at > stale_after_s`), per-agent `absent`/`error`. | Hard-coded | Q4 is unconfirmed, so the value is configurable |
| CSP | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src ipc: http://ipc.localhost` | `csp: null` (spike) | Exploration requirement |
| Edit / reload config | Menu "Edit config" calls a Rust handler that runs `tauri-plugin-opener` `open_path` on the fixed `hotbar.json` path (created with defaults first if missing), so the OS default editor opens it. No user input reaches it. The http/https rule applies only to `open:` cells. "Reload config" re-reads the file. | Spawn `notepad.exe`; expose `open_path` to JS | Fixed path, cross-platform, no JS permission |
| Capabilities | `core:default` + `core:window:allow-start-dragging` for windows `bar` and `panel`. The opener is used from Rust only, so it gets no JS permission. | Opener JS permissions | The spike gotcha (`core:default` required) is kept |

## Interfaces / Contracts

`project-usage.json` (`version` 1):

```json
{"version":1,"generated_at":"2026-10-15T12:00:00+02:00","currency":"USD",
 "agents":{"claude":{"status":"ok","cost_kind":"estimated",
   "totals":{"today":{"in":0,"out":0,"cw":0,"cr":0,"cost":0.0,"cost_partial":false},"7d":{},"30d":{},"month":{}},
   "projects":[{"key":"C:\\src\\repo","label":"repo","today":{},"7d":{},"30d":{},"month":{}}]},
  "codex":{"status":"absent"},"opencode":{"status":"error","cost_kind":"reported"}}}
```

- `status` is `ok`, `absent` (source not found) or `error` (kept from the last good blocks).
- `cost_kind` is `reported` (Pi, OpenCode), `estimated` (Claude, Codex) or `none` (reserved for later agents).
- `cost: null` means no price data. `totals` sum all projects. `projects` lists the top 30 by 30d tokens.

`hotbar.json`:

```json
{"version":1,"stale_after_s":300,"agents":["claude","codex","opencode","pi"],
 "cells":[{"id":"gh","label":"GH","action":"open:https://github.com"},
          {"id":"w","label":"W","action":"panel:C:\\tools\\w.exe","args":["--short"]}]}
```

An invalid cell is rendered disabled with its error. A config that fails to parse keeps the last good config and shows an error badge.

```python
class HotbarProcess:
    def __init__(self, exe_finder=find_hotbar_exe, popen=subprocess.Popen, pidfile=PIDFILE): ...
    def start(self) -> bool: ...   # stale cleanup, then spawn with CLAWDY_PARENT_PID
    def stop(self) -> None: ...    # idempotent, sync; safe from quit()
    @property
    def is_running(self) -> bool: ...
```

Rust modules in `hotbar/src-tauri/src/`: `main.rs` (builder, plugins, windows, menu), `watchdog.rs`, `usage.rs` (5 s mtime poll that emits `usage`), `config.rs`, `actions.rs`, `placement.rs`, `state.rs`, `pidfile.rs`.

## File Changes and PR Slicing (feature-branch chain, target at most 350 lines each)

| PR | Files | Est. lines |
|---|---|---|
| 1 | `usage_common.py` (new, with the `temp_root` seam); `claude_usage.py` refactored onto it with the exclusion; `test_usage_common.py`; `test_claude_usage.py`: the `reader()` helper and every direct `project_key` call pass a fake `temp_root` (otherwise `test_project_key_subfolder_resolves_to_git_root` and `test_project_key_git_file_counts_as_root` would turn None), and 3 tests change their expectations: `test_project_key_non_git_falls_back_to_cwd` (:72, now None), `test_project_key_nonexistent_and_relative_used_verbatim` (:76, now None), `test_monorepo_merges_and_temp_dir_is_own_project` (:98, the non-git `scratch` folder is now excluded) | 320 |
| 2 | `pi_usage.py`, `tests/test_pi_usage.py` + fixtures | 220 |
| 3 | `codex_usage.py` (+ `CODEX_PRICES`), `tests/test_codex_usage.py` + fixtures | 270 |
| 4 | `opencode_usage.py` (ro/immutable open), `tests/test_opencode_usage.py` (fixture WAL DB built in the test) | 280 |
| 5 | `usage_export.py`; `daemon.py` (reader list, file write); `tests/test_usage_export.py` | 230 |
| 6 | `hotbar/src-tauri/{Cargo.toml,build.rs,tauri.conf.json,capabilities/default.json}`, `main.rs`, `watchdog.rs`, `pidfile.rs`, single-instance + cargo tests | 250 |
| 7 | `usage.rs` (mtime poll + event), `placement.rs` + cargo tests, bar window with agent cells (`hotbar/ui/bar.{html,js}`, `style.css`) | 260 |
| 8 | `state.js`, `state.test.js`, `hotbar/ui/package.json` (`"type":"module"`, no deps), panel window (`panel.{html,js}`, `panel_side`) | 310 |
| 9 | `state.rs` (position, collapse, theme), context menu, Edit/Reload config | 240 |
| 10 | `config.rs`, `actions.rs` + cargo tests; UI custom cells | 330 |
| 11 | `hotbar_process.py`, `tests/test_hotbar_process.py`; `controller.py` (factory, start/quit/toggle), `preferences.py` (`hotbar_enabled: True`), `TrayState.hotbar_enabled`, `windows_tray.py`, `rumps_view.py`, controller tests, headless test | 340 |

The total is about 3,050 lines, against about 2,050 in the proposal. The proposal predates two things: the three extra readers with fixtures under strict TDD (about 800 lines with their tests), and the fresh per-PR estimates. The earlier design's total of 2,530 was a summing error; its own rows came to 2,730. PR 11 is independent of PRs 6-10 at test level (fake factory).

## Testing Strategy (strict TDD: RED first)

| Layer | RED tests |
|---|---|
| `usage_common` | A real git repo under an injected `temp_root` gives None, and the same repo outside it gives its key. With no `temp_root`, a git repo under `tmp_path` gives None, which proves the `gettempdir()` default. Non-git and relative cwd give None. A git-root `.git` file gives the key. Window boundaries in a fixed tz. Longest-prefix price. Tail reader: partial line deferred, truncation reset, per-file context kept across passes |
| Pi / Codex / OpenCode | Exact fixture totals per project and window. Reported cost summed, with `cost_partial` when one message lacks cost. Codex: `token_count` ignored, duplicate `response_id` counted once, unpriced model gives `null`. OpenCode: `part` ignored, a missing table gives `error` while the last snapshot is kept, a DB held by a live WAL writer connection is still readable, and its result matches committed rows only. A cleanly closed WAL DB (no `-wal`/`-shm`) is readable with the directory listing unchanged afterwards (no `-wal`/`-shm` created). A failed ro open while `-wal` exists gives `error` and never uses `immutable`. DB bytes are unchanged |
| Export | Schema keys. Written on an unchanged pass (mtime advances). An absent root gives `absent`. One reader raising leaves the other agents written. Atomic: no `.tmp` left behind. `set_project_usage` payload format unchanged (same keys and window shape; values may differ because of Q3) |
| Rust (`cargo test`) | `clamp` (off-screen, negative coords; monitor removed or no saved state gives right edge of primary, centred, 8 px), `panel_side` left/right/both-tight. Config: unknown prefix, `open:file://` rejected, `javascript:` rejected, empty program. `panel:` timeout kills the child, the output cap truncates. Pidfile round-trip |
| UI (`node --test`) | Cost formatting `$X`, `~$X (API-equiv.)`, `no price data`. Stale/missing/absent/error states. Today is the default window. Rows sorted by output tokens |
| Tray (pytest, fake popen) | Starts with `controller.start` when enabled. `quit` stops it, including the force-exit path. The toggle persists `hotbar_enabled` and starts or stops the hotbar. A missing exe logs a warning and nothing crashes. Exe lookup order. Stale kill only on an image path match; a mismatch or dead pid does not kill. `CLAWDY_PARENT_PID` passed. Headless: `daemon._build_daemon`/`main` with prefs `hotbar_enabled:true` never constructs or starts `HotbarProcess` (patched to raise) |
| Manual (Windows) | Proposal success criteria plus: no `msedgewebview2` left after a tray kill, and a fast tray restart still ends with exactly one hotbar |

## Threat Matrix

| Boundary | Applicability | Design response | RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: no file classification | — | — |
| Git repository selection | Applicable: project key walks to `.git` | Filesystem walk only; temp, relative and non-git excluded | `usage_common` rows |
| Commit / Push state | N/A: no VCS writes | — | — |
| PR / composed commands | Applicable (process): `run:`/`panel:`, hotbar spawn, `taskkill` | Argv only, no shell; programs resolved from config by id; open URLs limited to http/https; `taskkill` by verified PID | Config rejection cases, timeout/cap, image-path mismatch, argv assertions |

## Migration / Rollout

No migration. New files only appear under `~/.clawd-tank`. Behaviour change: Claude totals now exclude temp and non-git sessions (Q3). Rollback is per PR. `hotbar_enabled:false` disables the hotbar.

## Symbols apply must impact-check (GitNexus)

`project_key`, `ClaudeUsageReader` (`refresh`, `_read_file`, `_ingest`, `_prune`, `snapshot`), `_apply_cost`, `_price`, `PRICES`, `ClawdDaemon.__init__`, `_refresh_project_usage`, `_project_usage_checker`, `project_usage_to_payload`, `ClawdTankController` (`__init__`, `start`, `quit`, `_render`, `_shutdown_sequence`, `_kill_sim_now`), `TrayState`, `WindowsTrayView` menu build, `RumpsTrayView.build/render`, `preferences.DEFAULTS`.

## Open Questions

- [ ] Codex token inclusion (`input_tokens` ⊇ cached/cache-write?) to verify on a real rollout file at PR 3.
- [ ] OpenCode: when it stops writing the legacy `message` table, add a `session_message` path (detect with an empty legacy result alongside non-empty v2 tables).
- [ ] Q4: the 5-minute stale default is still unconfirmed by the user.
- [ ] SQLite `mode=ro` behaviour on a WAL DB without `-shm` varies by SQLite version (Python's bundled 3.4x). The PR 4 RED tests decide whether the `immutable` retry is ever reached.

## Revision log

- r2 (validator):
  - `temp_root` seam plus a RED test for the default.
  - All 3 changed Change 1 tests listed.
  - `set_project_usage` now checked for format, not bytes.
  - OpenCode WAL open strategy plus tests.
  - Re-sliced into 11 PRs of at most 340 lines; total reconciled at about 3,050.
  - Edit-config mechanism stated.
  - Headless test added.
  - Default placement stated for a removed monitor.
