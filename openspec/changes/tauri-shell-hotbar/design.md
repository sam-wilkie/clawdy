# Design: Tauri info hotbar (Change 2)

## Technical Approach

The daemon reads token usage for four agents and plan limits for three (Claude, Codex, Kiro), the Tauri hotbar shows it, and the tray owns the hotbar's lifetime. The daemon writes one file, `~/.clawd-tank/project-usage.json`, and the hotbar polls it. There is no new port or transport. Python keeps all parsing, prices and plan reading. Rust handles the window, placement, config and actions. The UI is vanilla HTML/JS (ES modules) with `withGlobalTauri` and no node dependencies.

    ~/.claude/projects  ~/.codex/sessions  opencode.db (ro)  ~/.gentle-shell/agent/sessions
            └──────────────┴── usage readers (usage_common) ──┴──────────┘
    statusline-cache.json  codex app-server  Kiro state.vscdb (ro)
            └──────────── plan sources (plan_usage) ────────────┘
                                   │ daemon, every 60 s, to_thread (Codex plan: 300 s)
                                   ▼
                  ~/.clawd-tank/project-usage.json (atomic, always rewritten)
                                   │ mtime poll 5 s
    tray ──spawn/kill──► clawdy-hotbar.exe ──event "usage"──► bar.html (dock) / panel.html
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
| Panel | A second hidden window, `panel`. Pure `panel_side(bar, edge, size, work_area)` puts it on the side facing into the screen, aligned with the bar along the edge and clamped. It hides on blur. An agent button opens it focused on that agent's card; the "all agents" button shows every card. | Resizing one window | The bar never moves |
| Placement | The bar is docked flush to an edge (`edge` in state: left, right, top, bottom). The window has a 12 px transparent margin, so it overhangs the work area by that margin on the docked side and the pill touches the edge. Pure `dock(rect, work_areas, primary)` picks the monitor containing the rect's centre and snaps to its nearest edge; pure restore puts a saved `edge` back and clamps along it. Otherwise (monitor removed, no saved state, rect fully off-screen) use the default: right edge of the primary work area, centred. Drag end is a quiet period after the last move event, then the bar snaps. Collapsing resizes the window to the collapsed pill on the same edge. | — | Unit-testable |
| Staleness (Q4) | `stale_after_s` in config, default 300. UI states: `missing` (no file or invalid on first read), `stale` (`now - generated_at > stale_after_s`), per-agent `absent`/`error`. | Hard-coded | Q4 is unconfirmed, so the value is configurable |
| CSP | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src ipc: http://ipc.localhost` | `csp: null` (spike) | Exploration requirement |
| Edit / reload config | Menu "Edit config" calls a Rust handler that runs `tauri-plugin-opener` `open_path` on the fixed `hotbar.json` path (created with defaults first if missing), so the OS default editor opens it. No user input reaches it. The http/https rule applies only to `open:` cells. "Reload config" re-reads the file. | Spawn `notepad.exe`; expose `open_path` to JS | Fixed path, cross-platform, no JS permission |
| Capabilities | `core:default` + `core:window:allow-start-dragging` for windows `bar` and `panel`. The opener is used from Rust only, so it gets no JS permission. | Opener JS permissions | The spike gotcha (`core:default` required) is kept |

### r3 decisions: plan-first dock (user-approved UI direction)

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Bar structure | Vertical pill dock on the screen edge: collapse chevron, one button per agent, "all agents" button, settings (gear opens the same menu as right-click, PR 9). Collapsed: a small pill with the chevron and one dot per agent. | Horizontal row of text cells (r2) | Approved mockup; fits a narrow edge dock |
| Agents | `claude`, `codex`, `opencode`, `kiro`, `pi`. `pi` is displayed as "Gentle Shell" everywhere in the hotbar; data ids never change. | Rename the id to `gentle` | Keeps the v1 file and existing readers stable |
| Plan first | `billing: "plan"` agents (Claude, Kiro, Codex with a ChatGPT login) show plan limits and no money. Money is shown only for `billing: "payg"` (OpenCode and Gentle Shell reported, Codex with an API key estimated). A file without `billing` (r2 daemon) is treated as `payg`, so nothing is hidden before PR 7b ships. | Show estimated cost for subscription users | An API-equivalent figure on a flat plan misleads; the limit is what the user can act on |
| Dock signal | Plan agent: ring = highest `used_pct` among its limits, stroked in the brand colour, cherry at >= 90 %; no ring when `plan` is absent, malformed or not `ok`. Payg agent: a small "$" badge. Read error: cherry badge. Stale file: badge on "all agents". Collapsed dot: brand colour; dimmed below 30 %; cherry with halo at >= 90 % or on agent `error`; track colour when `absent`. The collapsed tooltip names the agents needing attention (>= 90 % or error). | Traffic-light ring (green/orange/red) shown in the mockup copy | The approved brief specifies brand colour plus cherry; one alarm colour |
| Visual system | Tokens from the pets' approval card (`desktop/renderer/style.css` `#perm-card`, Mochi): `--surface #FFFFFF`, `--surface-2 #F6F1F0`, `--fg #2A1A22`, `--plum #5E4B5A`, `--muted #6E6470`, `--err #DE4553`, `--ok #28964A`, shadow `0 2px 8px rgba(42,26,34,.35)`, radius 12/8, chips 10 px 700 uppercase; text `system-ui, "Segoe UI"`, numbers `ui-monospace, Consolas`. Dark theme = the mockup's warm plum-ink set (`--surface #241A20`, `--surface-2 #2E222A`, `--fg #F6F1F0`, `--muted #B9AAB5`, `--err #F06B77`, `--ok #4CC071`). Default follows `prefers-color-scheme` until the user picks a theme. UI copy in Spanish, numbers via `Intl.NumberFormat("es-CO")` as in `desktop/renderer/dashboard.js`. | A new palette | Same family as the pets |
| Brand colours | Light / dark: Claude `#D97757`/`#E8906C`, Codex `#10A37F`/`#2DC79A`, Kiro `#9046FF`/`#AB7BFF`, Gentle Shell `#EB1889`/`#F2509F`, OpenCode ink `#2A1A22`/`#F6F1F0`. Used for rings, dots, plan bars and project share bars. | — | Mockup values |
| Logos | Dock: monochrome logos, `currentColor` SVGs from `hotbar/ui/assets/agents/{claude,codex,opencode,kiro}.svg` and `gentle-shell-mask.png` as a CSS mask (ink in light, white in dark). Panel: the original coloured logo beside the agent name (`gentle-shell.png` for Gentle Shell). | Coloured logos in the dock | The ring carries colour; logos stay legible on both themes |
| Pets | Each panel card shows the agent's idle pet: Claude `clawd-idle-living-v2.svg`, Codex `codex/cloud-idle-v2.svg`, Kiro/OpenCode/Gentle Shell `monster/monster-idle-v2.svg`, copied from `desktop/renderer/assets/` into `hotbar/ui/assets/pets/` with only the `viewBox` cropped to the sprite. Shipped in an asset-only PR (8b). | Reference the desktop folder | Tauri serves only `hotbar/ui`; a copy-only PR keeps authored diffs reviewable |
| Plan data shape | Additive, `version` stays 1: per agent `billing` and optional `plan {status, limits:[{id, label, used_pct, resets_at, window_min?}], reset_credits?, credits?{used, limit}}`. Kiro is a new plan-only entry (`cost_kind:"none"`, no `totals`/`projects`). The UI labels limits by `id` in Spanish and falls back to `label`. The Rust validator (`usage.rs valid_document`) is unchanged: it still requires only the four r2 agents and ignores `plan`; the UI validates `plan` and ignores a malformed one. | Version 2 | Old hotbars and old files keep working in both directions |
| Plan sources | New `host/clawd_tank_daemon/plan_usage.py`, kept apart from the token readers. Claude: `USAGE_CACHE_PATH` `rate_limits.five_hour/seven_day` (`used_percentage`, epoch `resets_at`), same fields as `protocol.read_usage_from_cache`. Kiro: `%APPDATA%/Kiro/User/globalStorage/state.vscdb` plus `User/profiles/*/globalStorage/state.vscdb` (`CLAWDY_KIRO_STATE_DB` override), files over 64 MiB skipped, opened `mode=ro` with the OpenCode retry rule, only `SELECT value FROM ItemTable WHERE key IN ('kiro.kiroAgent','kiro.kiroagent')`, `usageState.usageBreakdowns[type=CREDIT]` newest by `timestamp`. Codex: `codex app-server --listen stdio://` JSON-RPC (`initialize`, `account/read`, `account/rateLimits/read`), same exe lookup as `desktop/codex-usage.js`, `apiKey` account gives `billing:"payg"`. `build_document(readers, now, previous, plans=None)` merges plan results; a plan failure never affects token data. | Read plan data in Rust or JS | Python owns all parsing (r2); mirrors Electron's verified sources |
| Codex plan cadence | Refreshed every 300 s off-thread, last result kept between runs and on failure; billing changes only on a positive `account/read` answer. | Every 60 s | One process spawn per pass is heavy; limits move slowly |
| Gentle Shell path | `PiUsageReader` root = `$PI_CODING_AGENT_DIR/sessions` when set, else `~/.gentle-shell/agent/sessions`, the same resolution as `hooks.py` (:2713). Fixes the verified bug: `daemon.py:458` reads `~/.pi/agent/sessions`, stale since June. | Read both dirs | One source of truth with the extension installer |
| Slicing | PR 7 commits the Rust poll/placement with the existing placeholder bar; the dock rewrite is PR 7a. Plan data is PR 7b (Claude, Kiro, export, Gentle Shell path) and 7c (Codex app-server). Panel is PR 8 (model, window) and 8a (cards); pets are 8b. The collapsed pill moves to PR 9 with collapse. | One PR 7 with the rewrite (about 540 lines) | Keeps each authored diff at or under about 350 |

## Interfaces / Contracts

`project-usage.json` (`version` 1):

```json
{"version":1,"generated_at":"2026-10-15T12:00:00+02:00","currency":"USD",
 "agents":{"claude":{"status":"ok","cost_kind":"estimated",
   "totals":{"today":{"in":0,"out":0,"cw":0,"cr":0,"cost":0.0,"cost_partial":false},"7d":{},"30d":{},"month":{}},
   "projects":[{"key":"C:\\src\\repo","label":"repo","today":{},"7d":{},"30d":{},"month":{}}],
   "billing":"plan","plan":{"status":"ok","limits":[
     {"id":"session","label":"5h session","used_pct":62,"resets_at":"2026-10-15T14:14:00+02:00","window_min":300},
     {"id":"weekly","label":"Weekly","used_pct":38,"resets_at":"2026-10-18T16:00:00+02:00"}]}},
  "codex":{"status":"absent"},"opencode":{"status":"error","cost_kind":"reported","billing":"payg"},
  "kiro":{"status":"ok","cost_kind":"none","billing":"plan","plan":{"status":"ok",
   "limits":[{"id":"credits","label":"Cycle credits","used_pct":34,"resets_at":"2026-10-28T00:00:00Z"}],
   "credits":{"used":340,"limit":1000}}}}}
```

- `status` is `ok`, `absent` (source not found) or `error` (kept from the last good blocks).
- `cost_kind` is `reported` (Pi, OpenCode), `estimated` (Claude, Codex) or `none` (Kiro, which has no token data).
- `cost: null` means no price data. `totals` sum all projects. `projects` lists the top 30 by 30d tokens.
- r3, additive: `billing` is `plan` or `payg`. `plan.status` is `ok`, `no_data` (no cache or no limits), `signed_out`, `not_installed` or `error`; `limits` is present only when `ok`. Codex adds `reset_credits` (integer or null); Kiro adds `credits`. Absent `billing` means `payg`.

`hotbar.json`:

```json
{"version":1,"stale_after_s":300,"agents":["claude","codex","opencode","kiro","pi"],
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

# plan_usage.py (r3). Each source returns PlanResult or raises; the daemon catches per source.
PlanResult = dict  # {"status": "ok"|"absent", "billing": "plan"|"payg", "plan": {...} | None}
def read_claude_plan(cache_path, now) -> PlanResult: ...
def read_kiro_plan(paths, now) -> PlanResult: ...      # absent when no state.vscdb exists
class CodexPlanSource:                                   # 300 s cadence, keeps last result
    def __init__(self, exe_finder=find_codex_exe, popen=subprocess.Popen, timeout_s=15): ...
    def refresh(self, now) -> PlanResult: ...
def pi_sessions_root(env=os.environ, home=Path.home()) -> Path: ...  # lives in pi_usage.py
```

UI modules in `hotbar/ui/`: `state.js` (pure: agent list and display names, `billingOf`, `ringOf`, `dotOf`, `attention`, cost and number formatting, stale/missing rules), `bar.{html,js}` (dock), `panel.{html,js}` (cards), `style.css` (Mochi tokens, light and dark).

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
| 7 | `usage.rs` (mtime poll + event), `placement.rs` + cargo tests, `main.rs` wiring, existing placeholder bar (`bar.{html,js}`, `style.css`) as the run harness | 290 |
| 7a | Dock rewrite (r3): `hotbar/ui/package.json` (`"type":"module"`, no deps), `state.js` dock helpers + `state.test.js`, `bar.{html,js}`, `style.css` (Mochi tokens light/dark), `assets/agents/*` logos | 350 (split candidate) |
| 7b | `plan_usage.py` (Claude, Kiro), `usage_export.build_document(plans=)` + `billing`, Kiro entry, `daemon.py` wiring, `pi_usage.pi_sessions_root` + daemon root fix, tests (`test_plan_usage.py`, `test_usage_export.py`, `test_pi_usage.py`) | 330 |
| 7c | `CodexPlanSource` (exe lookup, app-server JSON-RPC, 15 s timeout, 300 s cadence, `apiKey` -> payg), daemon wiring, `test_codex_plan.py` with a fake app-server | 300 |
| 8 | `state.js` panel helpers + tests (cost rule, stale/missing/absent/error, rows), panel window (`panel.{html,js}` shell, `panel_side`, blur, focus by agent) | 320 |
| 8a | Panel cards: plan limit bars with reset times, Codex reset credits, Kiro credits grid, payg summary, token grid, project share bars, coloured logos | 300 |
| 8b | Pet assets copied into `hotbar/ui/assets/pets/` (viewBox crop only) and the card `<img>` | 15 authored (+ about 1,420 copied) |
| 9 | `state.rs` (position, collapse, theme), collapsed pill (dots, attention tooltip), context menu and gear button, Edit/Reload config | 280 |
| 10 | `config.rs`, `actions.rs` + cargo tests; UI custom cells | 330 |
| 11 | `hotbar_process.py`, `tests/test_hotbar_process.py`; `controller.py` (factory, start/quit/toggle), `preferences.py` (`hotbar_enabled: True`), `TrayState.hotbar_enabled`, `windows_tray.py`, `rumps_view.py`, controller tests, headless test | 340 |

The total is about 4,425 authored lines (PRs 1-6 about 1,570 as committed estimates, PRs 7-11 about 2,855), plus about 1,420 copied pet SVG lines in PR 8b that are not authored. r3 adds about 1,375 over r2: the plan sources (about 630 with tests), the plan-first dock and panel cards (about 600), and the collapsed pill. PR 11 is independent of PRs 6-10 at test level (fake factory); PRs 7b and 7c are host-only and independent of the UI PRs at test level.

## Testing Strategy (strict TDD: RED first)

| Layer | RED tests |
|---|---|
| `usage_common` | A real git repo under an injected `temp_root` gives None, and the same repo outside it gives its key. With no `temp_root`, a git repo under `tmp_path` gives None, which proves the `gettempdir()` default. Non-git and relative cwd give None. A git-root `.git` file gives the key. Window boundaries in a fixed tz. Longest-prefix price. Tail reader: partial line deferred, truncation reset, per-file context kept across passes |
| Pi / Codex / OpenCode | Exact fixture totals per project and window. Reported cost summed, with `cost_partial` when one message lacks cost. Codex: `token_count` ignored, duplicate `response_id` counted once, unpriced model gives `null`. OpenCode: `part` ignored, a missing table gives `error` while the last snapshot is kept, a DB held by a live WAL writer connection is still readable, and its result matches committed rows only. A cleanly closed WAL DB (no `-wal`/`-shm`) is readable with the directory listing unchanged afterwards (no `-wal`/`-shm` created). A failed ro open while `-wal` exists gives `error` and never uses `immutable`. DB bytes are unchanged |
| Export | Schema keys. Written on an unchanged pass (mtime advances). An absent root gives `absent`. One reader raising leaves the other agents written. Atomic: no `.tmp` left behind. `set_project_usage` payload format unchanged (same keys and window shape; values may differ because of Q3) |
| Rust (`cargo test`) | `clamp` (off-screen, negative coords; monitor removed or no saved state gives right edge of primary, centred, 8 px), `panel_side` left/right/both-tight. Config: unknown prefix, `open:file://` rejected, `javascript:` rejected, empty program. `panel:` timeout kills the child, the output cap truncates. Pidfile round-trip |
| Plan sources (r3, pytest) | Claude: fixture cache gives both limits with ISO `resets_at`; missing cache or no `rate_limits` gives `plan.status:"no_data"`. Kiro: fixture `state.vscdb` (built in the test) with a CREDIT breakdown gives `used_pct` and `credits`; newest profile wins; no DB gives `absent`; a row under another key is never read; DB bytes and directory listing unchanged; over 64 MiB skipped. Codex (fake app-server via fake popen): `chatgpt` account gives limits and `reset_credits`; `apiKey` gives `billing:"payg"` and no plan; signed out, timeout (child killed) and malformed lines keep the last result; argv is exact, no shell, `.cmd` shims rejected; refresh skipped inside 300 s. Export: `billing` for all five agents, Kiro entry without `totals`, a raising plan source leaves token data intact. Gentle Shell: `PI_CODING_AGENT_DIR` wins, default `~/.gentle-shell/agent/sessions`, daemon wiring uses it |
| UI (`node --test`) | Plan-first rule: money only for `billing:"payg"`, absent `billing` treated as payg. Ring = max `used_pct`, cherry at >= 90, none when `plan` absent, malformed or not `ok`. Dot classes (dim < 30, alert >= 90 or error, track when absent) and the attention list. `pi` displayed as "Gentle Shell". Cost formatting (es-CO USD, `≈` and "estimado" for estimated, "Sin precio" for null). Stale/missing/absent/error states. Today is the default window. Rows sorted by output tokens |
| Tray (pytest, fake popen) | Starts with `controller.start` when enabled. `quit` stops it, including the force-exit path. The toggle persists `hotbar_enabled` and starts or stops the hotbar. A missing exe logs a warning and nothing crashes. Exe lookup order. Stale kill only on an image path match; a mismatch or dead pid does not kill. `CLAWDY_PARENT_PID` passed. Headless: `daemon._build_daemon`/`main` with prefs `hotbar_enabled:true` never constructs or starts `HotbarProcess` (patched to raise) |
| Manual (Windows) | Proposal success criteria plus: no `msedgewebview2` left after a tray kill, and a fast tray restart still ends with exactly one hotbar |

## Threat Matrix

| Boundary | Applicability | Design response | RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: no file classification | — | — |
| Git repository selection | Applicable: project key walks to `.git` | Filesystem walk only; temp, relative and non-git excluded | `usage_common` rows |
| Commit / Push state | N/A: no VCS writes | — | — |
| PR / composed commands | Applicable (process): `run:`/`panel:`, hotbar spawn, `taskkill` | Argv only, no shell; programs resolved from config by id; open URLs limited to http/https; `taskkill` by verified PID | Config rejection cases, timeout/cap, image-path mismatch, argv assertions |
| Process integration: Codex app-server (r3) | Applicable: the daemon spawns `codex app-server --listen stdio://` | Fixed argv, no shell, native exe only (`.cmd`/`.bat` rejected), `CLAWDY_CODEX_BIN` must be an existing file, stderr discarded, no console window, 15 s timeout then kill, stdin closed and child reaped on every path; server-initiated requests answered `-32601`; never calls the reset-credit consume method | Fake popen: argv, timeout kill, `.cmd` rejection, malformed output, server request refused |
| Data exposure: Kiro state DB (r3) | Applicable: reads another app's SQLite store that also holds secrets | `mode=ro`, never writes or creates `-wal`/`-shm`; only the two `kiro.kiroAgent` keys are queried; only CREDIT numbers and the reset date leave the reader | Other-key row never read, DB bytes and listing unchanged |

## Migration / Rollout

No migration. New files only appear under `~/.clawd-tank`. Behaviour change: Claude totals now exclude temp and non-git sessions (Q3). Rollback is per PR. `hotbar_enabled:false` disables the hotbar. r3: the file stays `version` 1; until PR 7b ships every agent reads as payg (cost shown, no rings). After PR 7b, Gentle Shell totals jump from stale June data to current data.

## Symbols apply must impact-check (GitNexus)

`project_key`, `ClaudeUsageReader` (`refresh`, `_read_file`, `_ingest`, `_prune`, `snapshot`), `_apply_cost`, `_price`, `PRICES`, `ClawdDaemon.__init__`, `_refresh_project_usage`, `_project_usage_checker`, `project_usage_to_payload`, `ClawdTankController` (`__init__`, `start`, `quit`, `_render`, `_shutdown_sequence`, `_kill_sim_now`), `TrayState`, `WindowsTrayView` menu build, `RumpsTrayView.build/render`, `preferences.DEFAULTS`. r3: `build_document`, `PiUsageReader.__init__`, `read_usage_from_cache` (read only, not changed), `valid_document` (must stay unchanged).

## Open Questions

- [ ] Codex token inclusion (`input_tokens` ⊇ cached/cache-write?) to verify on a real rollout file at PR 3.
- [ ] OpenCode: when it stops writing the legacy `message` table, add a `session_message` path (detect with an empty legacy result alongside non-empty v2 tables).
- [x] Q4: the 5-minute stale default (`stale_after_s: 300`) is confirmed by the user.
- [ ] SQLite `mode=ro` behaviour on a WAL DB without `-shm` varies by SQLite version (Python's bundled 3.4x). The PR 4 RED tests decide whether the `immutable` retry is ever reached.
- [x] r3: Claude billing. Resolved 2026-10-21 (decided by the agent on the user's delegation; revisit if it misleads): Claude is `plan` only while the cache carries `rate_limits`; with none it is `payg` with `plan.status:"no_data"`, so an API-key user sees the estimated cost (`≈ … estimado`). This is what `plan_usage.read_claude_plan` does and `tests/test_plan_usage.py` pins; the old premise ("always plan") was out of date. Known edge: a subscription user whose statusLine cache is still empty (first run) briefly sees an estimate instead of limits.
- [x] r3: Codex billing default. Resolved 2026-10-21 (same delegation): `plan` before the first successful `account/read`, when signed out, and when Codex is not installed; a timeout keeps the previous billing. Only a positive answer flips it (`apiKey` gives `payg`, `chatgpt` gives `plan`), so subscription users never see a cost flash. Cost: an API-key user sees no money until the first read succeeds. Matches `CodexPlanSource` and `tests/test_codex_plan.py`.
- [ ] r3: the mockup's explanatory copy mentions green/orange rings from 70 %; the approved brief (brand colour, cherry at >= 90 %) is followed.

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
- r3 (user-approved UI direction, mockup `clawdy-hotbar-preview.html`):
  - Vertical pill dock, collapsed pill with per-agent dots, Mochi tokens with a plum-ink dark theme, Spanish copy.
  - Five agents: Kiro added as a plan-only entry; `pi` displayed as "Gentle Shell".
  - Plan-first display; money only for payg agents; rings from the new additive `plan` block.
  - New plan sources (Claude statusline cache, Codex app-server, Kiro state DB) and the Gentle Shell sessions path fix.
  - Monochrome dock logos, coloured panel logos, idle pets per card.
  - Re-sliced PRs 7-9 into 7, 7a, 7b, 7c, 8, 8a, 8b, 9; total about 4,425 authored lines.
  - Threat matrix rows added for the Codex app-server spawn and the Kiro DB read.
