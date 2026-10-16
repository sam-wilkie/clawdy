# Plan Usage Reader Specification

## Purpose

Read-only collection of subscription plan limits for Claude, Codex and Kiro, and the Codex billing mode, from the same local sources the Electron pet dashboard uses (`desktop/agent-usage.js`, `desktop/codex-usage.js`). Results feed the `billing` and `plan` fields of `project-usage.json` (see project-usage-file). Plan reading is independent of token aggregation.

## Requirements

### Requirement: Claude plan from the statusline cache

The reader MUST read `~/.clawd-tank/statusline-cache.json` `rate_limits.five_hour` and `rate_limits.seven_day` and produce limits `session` (window 300 min) and `weekly` from `used_percentage`, with `resets_at` converted from epoch seconds to ISO-8601 with offset. A limit whose percentage is missing, negative or not a number MUST be omitted. A missing or unreadable cache, or one with neither limit, MUST give `plan.status` `no_data`. The reader MUST NOT write the cache.

#### Scenario: Both limits
- GIVEN a cache with five-hour 62 % resetting at epoch E and seven-day 38 %
- WHEN read
- THEN `plan.status` is `ok` with `session` 62 (`resets_at` = E as ISO-8601) and `weekly` 38

#### Scenario: Only weekly
- GIVEN a cache whose `five_hour` lacks `used_percentage`
- WHEN read
- THEN only the `weekly` limit is present

#### Scenario: No cache
- GIVEN no statusline cache file
- WHEN read
- THEN `plan.status` is `no_data` and no error is raised

### Requirement: Codex plan and billing from the app-server

The reader MUST resolve a native Codex executable in the order `CLAWDY_CODEX_BIN` (existing file), `PATH`, `$CODEX_HOME/packages/app-server-daemon/releases/*`, `%LOCALAPPDATA%/OpenAI/Codex/bin/*`, then the npm package's native vendor binary; script shims (`.cmd`, `.bat`) MUST be rejected. It MUST run `codex app-server --listen stdio://` with a fixed argument list, no shell, no console window and stderr discarded, send `initialize`, `initialized`, `account/read` (`refreshToken: false`) and `account/rateLimits/read`, and end the child (stdin closed, killed if still alive after 500 ms) on every path. The whole exchange MUST time out after 15 s, killing the child. Server-initiated requests MUST be answered with error `-32601`. The reader MUST NOT call the reset-credit consume method.

From the `codex` bucket (`rateLimitsByLimitId.codex`, else `rateLimits` with no `limitId` or `limitId` `codex`) it MUST produce limits `primary` and `weekly` from `primary`/`secondary` `usedPercent`, with `window_min` from `windowDurationMins` and `resets_at` from `resetsAt`, plus `reset_credits` from `rateLimitResetCredits.availableCount` (non-negative integer, else `null`). An `apiKey` account MUST give `billing` `payg` and no plan block. No account MUST give `plan.status` `signed_out`; no executable `not_installed`; a timeout, process error or JSON-RPC error `error`; no `codex` bucket `no_data`.

#### Scenario: ChatGPT account
- GIVEN a fake app-server answering a `chatgpt` account and a `codex` bucket with primary 21 % (300 min) and secondary 47 %, with 2 reset credits
- WHEN refreshed
- THEN `billing` is `plan` and `plan` holds `primary` 21 (`window_min` 300), `weekly` 47 and `reset_credits` 2

#### Scenario: API key account
- GIVEN a fake app-server answering an `apiKey` account
- WHEN refreshed
- THEN `billing` is `payg`, no plan block is produced, and `account/rateLimits/read` is not sent

#### Scenario: Timeout
- GIVEN a fake app-server that never answers
- WHEN 15 s pass
- THEN the child is killed, `plan.status` is `error`, and the previous `billing` is kept

#### Scenario: Script shim rejected
- GIVEN the only `codex` on `PATH` is `codex.cmd`
- WHEN the executable is resolved
- THEN it is rejected and, with no other candidate, `plan.status` is `not_installed`

#### Scenario: Server request refused
- GIVEN the app-server sends a request with an id before answering
- WHEN the reader receives it
- THEN it replies with error `-32601` and continues the exchange

### Requirement: Codex cadence

The Codex plan MUST be refreshed at most every 300 s, off the event loop. Between refreshes and after a failure, the last result MUST be reused. `billing` MUST change only on a successful `account/read`; before the first one it MUST be `plan`.

#### Scenario: Within cadence
- GIVEN a successful refresh 60 s ago
- WHEN the daemon pass runs
- THEN no process is spawned and the previous result is used

### Requirement: Kiro plan from the state database

The reader MUST look for `state.vscdb` under the Kiro user dir (`%APPDATA%/Kiro/User` on Windows, `~/Library/Application Support/Kiro/User` on macOS, `$XDG_CONFIG_HOME/Kiro/User` or `~/.config/Kiro/User` elsewhere) in `globalStorage/` and every `profiles/*/globalStorage/`; `CLAWDY_KIRO_STATE_DB` MUST replace that list. Files over 64 MiB MUST be skipped. Each DB MUST be opened read-only with the OpenCode open rule (`mode=ro`, `immutable=1` retry only without `-wal`) and queried only with `SELECT value FROM ItemTable WHERE key IN ('kiro.kiroAgent', 'kiro.kiroagent')`. From `kiro.resourceNotifications.usageState.usageBreakdowns`, the `CREDIT` item with numeric `currentUsage` and positive `usageLimit` MUST give limit `credits` (`used_pct` = used / limit x 100, `resets_at` from `resetDate`) and `credits` `{used, limit}`; across files the cache with the newest `timestamp` wins. No DB file MUST give the Kiro entry `absent`; DBs without a usable cache give `plan.status` `no_data`. A malformed value or unreadable DB MUST be skipped without aborting the pass.

#### Scenario: Credit cache
- GIVEN a test-built `state.vscdb` with a CREDIT breakdown of 340 used of 1000
- WHEN read
- THEN `credits` is `{used: 340, limit: 1000}` and the `credits` limit is 34 %

#### Scenario: Newest profile wins
- GIVEN the default DB with timestamp 100 and a profile DB with timestamp 200
- WHEN read
- THEN the profile DB's figures are used

#### Scenario: Other keys never read
- GIVEN a DB with a secret-storage row next to the Kiro row
- WHEN read
- THEN only the `kiro.kiroAgent` row is selected, and the DB bytes and directory listing are unchanged afterwards

#### Scenario: No Kiro install
- GIVEN no `state.vscdb` in any location
- WHEN read
- THEN the Kiro entry is `absent` and no error is raised

### Requirement: Isolation

A plan source that raises MUST be caught per source and logged once per distinct failure; it MUST NOT affect token readers, other plan sources, session handling, or the file write.

#### Scenario: One source raises
- GIVEN the Kiro source raises
- WHEN the daemon pass runs
- THEN Claude and Codex plan data and all token data are written normally
