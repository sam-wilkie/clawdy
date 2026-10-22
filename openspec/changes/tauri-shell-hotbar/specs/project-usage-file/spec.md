# Project Usage File Specification

## Purpose

The daemon exports per-agent, per-project usage to `~/.clawd-tank/project-usage.json` for the hotbar. The file is the only data interface between daemon and hotbar.

## Requirements

### Requirement: Schema

The file MUST be one JSON object with `version` (1), `generated_at` (ISO-8601 with offset), `currency` (`USD`) and an `agents` object keyed by agent id (`claude`, `codex`, `opencode`, `pi`). Each agent entry MUST carry `status`: `ok`, `absent` (source not found) or `error` (reader failed; blocks kept from the last good pass). An `ok` or `error` entry MUST carry `cost_kind` (`reported` for Pi and OpenCode, `estimated` for Claude and Codex; `none` is reserved) and, when data exists, `totals` (sum over all projects) and `projects` (top 30 by 30d tokens). Per window (`today`, `7d`, `30d`, `month`) the figures are `in`, `out`, `cw`, `cr`, `cost` (number or `null` = no price data) and `cost_partial`. Each project has `key` and `label`. Adding an agent MUST NOT change the schema of existing ones.

#### Scenario: Four agents
- GIVEN readers returning data for all four agents
- WHEN the file is written
- THEN it matches the schema, Pi/OpenCode have `cost_kind` `reported` and Claude/Codex `estimated`

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
