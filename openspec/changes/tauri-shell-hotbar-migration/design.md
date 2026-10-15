# Design: Shell-agnostic daemon groundwork (Change 1)

## Technical Approach

Four stacked host-only PRs, each additive and revertible alone. No Tauri, firmware, BLE or Electron code changes. Headless entry point: `python -m clawd_tank_daemon.daemon` (no package `__main__` is added).

| PR | Unit | Lines |
|---|---|---|
| 1 | Usage reader (pure, no daemon wiring) | 390 |
| 2 | `set_project_usage` to `desktop_pet` transports | 170 |
| 3 | Hook executable resolution + `ensure_hooks_current()` | 173 |
| 4 | Headless parity (preferences, hooks, legacy autostart opt-out) | 182 |
| | **Total** | **915** |

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Reader module | One `claude_usage.py`: parser, aggregator, dated `PRICES` | Separate pricing module | Same size; a price update is a one-dict edit |
| Aggregation | Daily buckets `(project_key, local_date, model) -> [in, out, cw5m, cw1h, cr]`, 62-day retention | Raw records | Bounded memory; all windows derivable |
| Files read | `root.rglob("*.jsonl")`, including `**/subagents/*.jsonl` | Main sessions only | Subagent usage is real spend. Verified: 1 overlapping `message.id` of ~5,900, absorbed by dedup |
| Dedup | Global `seen` on `message.id + requestId`, pruned with buckets | Per-file dedup | One line per content block; resumed sessions copy history |
| Incremental read | Per-file `{offset, size}`, `open(path, "rb")`, complete lines only; `size < offset` resets to 0 | Re-parse all | Cheap after first scan; dedup absorbs replays |
| Timestamps | `timestamp` is ISO-8601 UTC with `Z`; parse via `fromisoformat(s.replace("Z", "+00:00"))`, bucket by `ts.astimezone(tz)` (`tz=None` = system local, DST-aware) | Naive parse | Tests inject a fixed tz |
| Cadence | Dedicated `_project_usage_checker`, 60 s, `await asyncio.to_thread(reader.refresh)` in one sequential task; immediate send of the cached snapshot when a `desktop_pet` transport connects | Piggy-back on 15 s `_usage_checker` | Rescanning every 15 s gains nothing; one in-flight call needs no lock |
| Project key | Walk up from `cwd` to first `.git` (dir or file), else `cwd`; cached; label = basename | `git rev-parse` subprocess | No spawn, no missing-git failure |
| Cost | Per model share. Unpriced share: `cost: null`. Window `cost` = sum of priced shares; `cost_partial: true` if any share with tokens is unpriced; `cost: null` only if no share is priced | All-or-nothing null | Local logs contain unlisted ids (e.g. `claude-fable-5-1`); one would null every total |
| Model match | Longest prefix over version-specific keys (`claude-opus-4-1`, not `claude-opus-4`) | Family prefixes | An unlisted new version becomes unpriced instead of borrowing a sibling's price |
| Cache tiers | `usage.cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` priced separately; if `cache_creation` absent, all `cache_creation_input_tokens` are 5m | One write rate | Both fields present in local jsonl; 1h costs 2x input vs 1.25x |
| Gating | Send only when `getattr(t, "desktop_pet", False) and t.is_connected`; skip if payload equals last sent | Version gate | BLE/SDL never carry the flag; no protocol bump |
| Failure isolation | Checker catches `Exception` per pass, logs, keeps last payload; separate task from `_usage_checker` | Shared task | `set_usage` cannot be starved by the reader |
| Hook resolution | `resolve_hook_executable(platform, frozen, executable, env)` returns `<dir>\margarita-notify.exe` when frozen on Windows and `CLAWD_TANK_HOOK_EXE_DIR` is valid, else `executable`. It feeds **both** `build_hook_command` (notify) and `build_statusline_command` (statusline, via `dirname`), plus codex and antigravity call sites | Copying exes to `~/.clawd-tank/bin` | Onedir exe needs `_internal/`; builders stay byte-identical |
| Override validity | Absolute dir, contains both `margarita-notify.exe` and `margarita-statusline.exe`, no `"` in path; else ignored + warning | Trust env | The path is composed into a `cmd.exe` line |
| Missing exe | `ensure_hooks_current()` skips install when the resolved frozen notify exe is missing; stale paths re-point via exact-match `are_hooks_installed()` + `_OUR_COMMAND_RE` prune | New re-point logic | Existing behavior; tests lock it |
| Hook ownership | One `hooks.ensure_hooks_current()` (from `app.py:56-61`, `__main__.py:117-122`). Tray always calls it. Headless calls it only after winning the lock and without `--no-install-hooks`. Legacy autostart (`host/clawd-tank-notify:88`) passes `--no-install-hooks` | Both install freely | Tray running: headless exits at lock, writes nothing. Autostarted daemon never flips tray hooks |
| Startup errors | Startup callable wrapped in `try/except Exception` + log | Propagate | Corrupt `settings.json` must not abort the daemon |
| Layering | `daemon.main()` lazily imports `clawd_tank_menubar.hooks` / `.preferences` (stdlib-only; package `__init__` empty) | Move `hooks.py` | 2,600-line move breaks test imports |
| Prefs loader | `load_preferences()` gains an `isinstance(stored, dict)` guard | New loader | Today a `[1]` file raises `AttributeError` on `.pop` |

### Headless preference mapping (CLI flags win)

If any of `--sim`, `--sim-only`, `--sim-port` is given, transports follow today's CLI logic and `ble_enabled`/`sim_enabled` are ignored.

| Key | Headless behavior |
|---|---|
| `ble_enabled` | `false` → no BLE transport |
| `sim_enabled` | `true` (default) → `SimClient` on `SIM_DEFAULT_PORT`; retries at debug log level when nothing listens |
| `sim_desk_mode` | `true` and sim enabled → `SimClient(desktop_pet=True)` (mirrors `controller.py:135`) |
| `sim_window_visible` | Ignored (tray/UI-only): drives window commands to a sim process the tray spawns; headless spawns none |
| `sim_always_on_top` | Ignored (tray/UI-only): `start_pinned` of `SimProcessManager`, same reason |
| `enable_opencode` | Unchanged: already read by `ClawdDaemon` via `_load_preferences()` |

## Data Flow

    ~/.claude/projects/**/*.jsonl  (read-only, "rb")
        │ to_thread, every 60 s, incremental
        ▼
    ClaudeUsageReader.refresh() → snapshot(now) → project_usage_to_payload()
        ▼
    _broadcast_project_usage() ──► desktop_pet SimClient (also on connect)
                               ✗  BLE, SDL sim

## Interfaces / Contracts

```python
class ClaudeUsageReader:
    def __init__(self, root: Path, tz: tzinfo | None = None, retention_days: int = 62): ...
    def refresh(self) -> None: ...                      # blocking; thread only
    def snapshot(self, now: datetime) -> list[dict]: ...
def project_key(cwd: str) -> str: ...
def resolve_hook_executable(platform: str, frozen: bool, executable: str, env: Mapping[str, str]) -> str: ...
```

```json
{"action":"set_project_usage","currency":"USD","estimate":true,
 "projects":[{"key":"C:/src/repo","label":"repo",
   "today":{"in":0,"out":0,"cw":0,"cr":0,"cost":0.0,"cost_partial":false},
   "7d":{...},"30d":{...},"month":{...}}]}
```

- `cw` = 5m + 1h writes. `cost_partial: true` adds `"unpriced":["<model>"]` to that window.
- Windows use local days: `today`; `7d`/`30d` include today; `month` from the 1st. Max 30 projects with non-zero 30d/month usage, sorted by 30d tokens (one line under ~15 KB).

### PRICES (USD per MTok; multipliers 5m write 1.25x, 1h write 2x, read 0.1x)

Source: https://docs.anthropic.com/en/docs/about-claude/pricing. Status: **to verify at implementation** (no fetch available to the design executor on 2026-10-13); the apply phase records the verified as-of date per row.

| Prefix | Input | Output |
|---|---|---|
| `claude-opus-4-5` | 5 | 25 |
| `claude-opus-4-1` | 15 | 75 |
| `claude-opus-4-2025` | 15 | 75 |
| `claude-sonnet-4-5` | 3 | 15 |
| `claude-sonnet-4-2025` | 3 | 15 |
| `claude-haiku-4-5` | 1 | 5 |
| `claude-3-5-haiku` | 0.80 | 4 |

Long-context (>200K) Sonnet surcharge is not modeled (estimate).

## File Changes

| File | PR | Action | Lines |
|---|---|---|---|
| `host/clawd_tank_daemon/claude_usage.py` | 1 | Create | 180 |
| `host/tests/test_claude_usage.py` | 1 | Create | 210 |
| `host/clawd_tank_daemon/protocol.py` | 2 | `project_usage_to_payload` | 15 |
| `host/clawd_tank_daemon/daemon.py` | 2 | checker task, broadcast, connect send, shutdown | 45 |
| `host/tests/test_project_usage_transport.py` | 2 | Create | 110 |
| `host/clawd_tank_menubar/hooks.py` | 3 | resolver, guard, `ensure_hooks_current` | 45 |
| `host/clawd_tank_menubar/app.py`, `__main__.py` | 3 | call helper | 14 |
| `host/tests/conftest.py` | 3 | `delenv` override, resolver | 4 |
| `host/tests/test_hook_resolution.py` | 3 | Create (goldens) | 110 |
| `host/clawd_tank_daemon/daemon.py` | 4 | `main()` prefs/flags, `startup` param | 45 |
| `host/clawd_tank_menubar/preferences.py` | 4 | non-object guard | 3 |
| `host/clawd-tank-notify` | 4 | autostart `--no-install-hooks` | 2 |
| `host/tests/test_headless_startup.py` | 4 | Create | 132 |
| | | **Total** | **915** |

If PR1 measures over 400 at apply, split pricing (`PRICES` + cost tests) into PR1b.

## Testing Strategy (strict TDD: RED first per row)

| Unit | RED tests |
|---|---|
| Reader totals | Fixture totals per project/window; duplicate `message.id+requestId` counted once; subagent file included; monorepo subfolders merge; temp `cwd` own key |
| Tolerant parsing | Garbage line; entry without `usage`; missing `cache_read_input_tokens` = 0; unreadable file (dir named `bad.jsonl`) skipped; no exception escapes |
| Incremental | Partial trailing line deferred; append 2 lines between passes → totals grow by exactly them; truncated file not double-counted; no `projects` dir → empty, no error; 62-day prune |
| Read-only | Tree snapshot (paths, sizes, mtimes) under fake root identical after refresh |
| Time | tz UTC-8, today 2026-10-13: `2026-10-14T07:59:59Z` is today, `08:00:00Z` is not; month reset |
| Cost | Known model within 0.01 of hand calc; 1h cache tier at 2x vs 5m at 1.25x; no `cache_creation` → 5m; unpriced share `null`, total = priced sum + `cost_partial`; all unpriced → `null`; `claude-opus-4-6` unpriced |
| Transport | Only pet receives; BLE/sim payloads unchanged; unchanged snapshot not resent; pet connect sends cached snapshot immediately; reader raises → `set_usage` still sent and error logged; `set_project_usage` interleaved with `permission_request` → request bytes and decision resolution unchanged |
| Hooks | Goldens for notify **and** statusline: frozen-win, dev-win, pythonw, POSIX unchanged; env override changes both; invalid override (relative, missing exe, `"` in path) ignored; missing frozen exe leaves settings untouched; old exe path re-pointed; second `ensure_hooks_current` writes nothing |
| Headless | Prefs missing / `{not json` / `[1]` → defaults, file bytes unchanged; `ble_enabled:false` → no BLE; `sim_enabled:true` with no flag → sim transport; `sim_enabled:false` + `--sim` → sim; `sim_desk_mode` → `desktop_pet`; `--sim-only --sim-port 12345` → today's transports/port; `--no-install-hooks` skips callback; callback only after lock; lost lock → no write; corrupt `settings.json` → daemon runs, file unchanged; legacy autostart argv contains `--no-install-hooks` |

## Threat Matrix

| Boundary | Applicability | Design response | RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: no file classification or execution | — | — |
| Git repository selection | Applicable: key derives repo root from `cwd` | Filesystem walk only; absolute `cwd` authoritative; relative/missing `cwd` used verbatim | Subfolder, relative, nonexistent, `.git` file |
| Commit state | N/A: no VCS writes | — | — |
| Push state | N/A | — | — |
| PR commands / composed commands | Applicable: env dir composed into a `cmd.exe` hook line; autostart argv | Override validity rule above; argv list (no shell) | Invalid-override cases; autostart argv test |

## Migration / Rollout

No data migration. Reader only reads `~/.claude`. Hooks roll back via startup auto-update or `--uninstall-hooks`; the env override is unset by default, so output equals today's.

## Blast radius (grep; gitnexus unavailable to this executor)

- `build_*` signatures unchanged; `HOOK_COMMAND` → `KIRO_HOOK_COMMAND`, `_command_is_current`, conftest, `test_hooks_install.py:314`.
- `daemon.main` → `start-daemon.bat`, README, `host/clawd-tank-notify:88` (now opt-out).
- `ClawdDaemon.__init__`/`run` → `controller.start` (`headless=False`), test `make_daemon`; new params default to today.
- `load_preferences` → controller, tests (guard only changes the crash case).

## Open Questions

- [ ] Headless with no prefs file now also runs an idle `SimClient` (DEFAULTS `sim_enabled: true`). Accepted for tray parity; confirm.

## Revision log

- design: cadence, per-share cost, cache tiers, pref mapping, autostart opt-out, env drives both exes, reconciled lines (915), expanded RED tests, PRICES status.
- proposal: entry point, cadence, unpriced semantics, workload forecast.
- claude-usage-reader spec: cache tier fields, per-share cost + `cost_partial`, 1h scenario.
- project-usage-transport spec: 60 s cadence, connect send, unpriced scenario.
- headless-daemon spec: entry point, lock-owner rule, legacy autostart, pref mapping.
- hook-command-resolution spec: env override drives notify and statusline.
