# Project Usage File Specification

## Purpose

The daemon exports per-agent, per-project usage to `~/.clawd-tank/project-usage.json` for the hotbar. The file is the only data interface between daemon and hotbar.

## Requirements

### Requirement: Schema

The file MUST be one JSON object with `version` (1), `generated_at` (ISO-8601 with offset), `currency` (`USD`) and an `agents` object keyed by agent id (`claude`, `codex`, `opencode`, `pi`, `kiro`). Each agent entry MUST carry `status`: `ok`, `absent` (source not found) or `error` (reader failed; blocks kept from the last good pass). An `ok` or `error` entry MUST carry `cost_kind` (`reported` for Pi and OpenCode, `estimated` for Claude and Codex, `none` for Kiro) and, when token data exists, `totals` (sum over all projects) and `projects` (top 30 by 30d tokens). Per window (`today`, `7d`, `30d`, `month`) the figures are `in`, `out`, `cw`, `cr`, `cost` (number or `null` = no price data) and `cost_partial`. Each project has `key` and `label`. Adding an agent or an optional field MUST NOT change the schema of existing ones, and `version` MUST stay 1.

#### Scenario: Five agents
- GIVEN readers returning data for all four token agents and a Kiro plan cache
- WHEN the file is written
- THEN it matches the schema, Pi/OpenCode have `cost_kind` `reported`, Claude/Codex `estimated` and Kiro `none`

#### Scenario: Kiro entry has no token data
- GIVEN a readable Kiro credit cache
- WHEN the file is written
- THEN `agents.kiro` has `status` `ok`, `billing` `plan` and a `plan` block, and no `totals` or `projects`

#### Scenario: Kiro absent
- GIVEN no Kiro `state.vscdb` in any profile
- WHEN the file is written
- THEN `agents.kiro` is `{"status":"absent"}`

#### Scenario: Absent agent
- GIVEN Codex sessions directory does not exist
- WHEN the file is written
- THEN `agents.codex` is `{"status":"absent"}` and other agents are unaffected

#### Scenario: Reader error keeps last good
- GIVEN OpenCode succeeded once, then its reader reports a failure
- WHEN the file is written
- THEN `agents.opencode.status` is `error` and its `totals`/`projects` are the last good blocks

#### Scenario: Top 30
- GIVEN 40 projects with usage
- WHEN written
- THEN `projects` holds the 30 with the most 30d tokens and `totals` still sum all 40

### Requirement: Billing and plan block

Every non-`absent` entry MUST carry `billing`: `plan` or `payg`. Claude and Kiro MUST be `plan`; OpenCode and Pi MUST be `payg`; Codex MUST be `payg` only after the plan reader reports an API-key account, and `plan` otherwise. A `plan` agent MAY carry `plan` `{status, limits, reset_credits?, credits?}` where `status` is `ok`, `no_data`, `signed_out`, `not_installed` or `error`. When `status` is `ok`, `limits` MUST be a non-empty list of `{id, label, used_pct, resets_at}` with optional `window_min`; `used_pct` is a number from 0, `resets_at` is ISO-8601 with offset or `null`. A limit with no percentage MUST be omitted. Codex MAY add `reset_credits` (integer or `null`); Kiro MUST add `credits` `{used, limit}`. A plan source failure MUST NOT change the agent's token blocks or `status`, and MUST NOT prevent the file from being written; the last good `plan` block is kept with `plan.status` `error`. For Kiro, which has no token data, a failure after a good pass gives `status` `error` with the last good `plan` block.

#### Scenario: Claude limits
- GIVEN a statusline cache with five-hour 62 % and seven-day 38 %
- WHEN the file is written
- THEN `agents.claude.plan.limits` holds `session` 62 and `weekly` 38 with their reset times and `billing` is `plan`

#### Scenario: Codex on an API key
- GIVEN the Codex plan reader reports an API-key account
- WHEN the file is written
- THEN `agents.codex.billing` is `payg`, it has no `plan` block and its token blocks are unchanged

#### Scenario: Plan source raises
- GIVEN the Claude plan source raises after a good pass
- WHEN the refresh runs
- THEN the file is written, the error is logged, Claude's token blocks and `status` are unchanged, and its last good `plan` is kept with `plan.status` `error`

#### Scenario: Older consumer
- GIVEN a hotbar that only knows the r2 fields
- WHEN it reads the file
- THEN the four r2 agents still validate and the extra fields are ignored

### Requirement: Atomic write

The daemon MUST write via a temp file in the same directory and an atomic replace. A reader MUST never observe a partial file. If the replace fails (for example the file is held open on Windows), the daemon MUST log and retry on the next pass without blocking.

#### Scenario: Interrupted write
- GIVEN a write fails midway
- WHEN the hotbar reads
- THEN it sees the previous complete file and no temp file is left behind

#### Scenario: Replace denied
- GIVEN the replace raises a permission error
- WHEN the pass ends
- THEN the error is logged, the daemon continues, and the next pass writes normally

### Requirement: Write cadence

The daemon MUST write on every 60 s refresh, even when nothing changed, so `generated_at` shows daemon liveness. A failure in one agent's reader MUST NOT prevent writing the others, and MUST NOT interrupt session handling or the existing Claude `set_project_usage` payload. The payload format (action name, keys, shape) MUST stay unchanged; its values may differ because of the exclusion rule.

#### Scenario: Unchanged data
- GIVEN two refreshes with identical aggregates
- WHEN both complete
- THEN the file is rewritten and the second `generated_at` is later

#### Scenario: One reader raises
- GIVEN the OpenCode reader fails
- WHEN the refresh runs
- THEN the file is written with the other agents and the error is logged

### Requirement: Exclusion rule

The file MUST contain no project from a temp dir, a relative path, or outside a git repo. This rule is applied once by the shared readers, not re-implemented at export.

#### Scenario: Excluded cwd
- GIVEN usage whose cwd is a temp dir
- WHEN the file is written
- THEN no project for it exists in any agent entry
