# Claude Usage Reader Specification

## Purpose

Read-only, offline aggregation of Claude Code token usage and estimated cost per project from `~/.claude/projects/**/*.jsonl`. Fields used: `cwd`, `message.model`, `message.usage.{input,output,cache_creation_input,cache_read_input}_tokens`, `message.usage.cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens`, and the entry `timestamp` (ISO-8601 UTC with `Z`). Files are read recursively, including `**/subagents/*.jsonl`.

## Requirements

### Requirement: Per-project aggregation

The reader MUST total input, output, cache-creation and cache-read tokens per project key, for windows today, last 7 days, last 30 days and calendar month. The project key SHALL be the git root of `cwd`, else `cwd` itself; the label SHALL be the key's basename. One shared function MUST compute the key. A `cwd` in a temp directory or outside any git repo MUST fall back to `cwd`. Subfolders of one repo MUST merge into one project.

#### Scenario: Fixture totals
- GIVEN a fixture jsonl with 3 assistant entries in one repo
- WHEN the reader aggregates
- THEN token totals equal the hand-computed sums per window

#### Scenario: Monorepo subfolders and non-git cwd
- GIVEN entries with `cwd` `repo/a` and `repo/b` (same git root), and one `cwd` in a temp dir
- WHEN aggregated
- THEN `repo` is one project and the temp dir is its own project keyed by `cwd`

### Requirement: Tolerant parsing

The reader MUST NOT raise on bad input. Malformed JSON lines, a truncated last line, entries without `message.usage`, missing individual token fields (counted as 0), and unreadable files SHALL be skipped and logged, never aborting the pass.

#### Scenario: Malformed and partial data
- GIVEN a file with a garbage line, an entry lacking `usage`, and an entry lacking `cache_read_input_tokens`
- WHEN aggregated
- THEN valid entries are counted, the missing field counts as 0, and no exception escapes

### Requirement: Time windows

Windows MUST be evaluated in the user's local timezone. Timestamps are UTC ISO strings. An entry at 23:59:59 local belongs to that local day; one second later belongs to the next. Calendar month MUST reset at local month start. Entries without a parseable timestamp SHALL be skipped.

#### Scenario: Day boundary
- GIVEN local timezone UTC-8 and an entry at `2026-10-14T07:59:59Z`
- WHEN "today" is 2026-10-13 local
- THEN the entry counts as today; an entry at `08:00:00Z` does not

### Requirement: Estimated cost

Cost SHALL be computed from a built-in, dated, sourced price table, labeled "API-equivalent estimate", with no network access. Cache-read, 5-minute cache-write and 1-hour cache-write tokens MUST each use their own rates; when `cache_creation` is absent, all `cache_creation_input_tokens` SHALL be priced as 5-minute writes. A model absent from the table MUST yield `cost: null` for its share, never 0 and never an exception. A window's total `cost` SHALL be the sum of its priced shares, with `cost_partial: true` when any share with tokens is unpriced, and `null` when no share is priced.

#### Scenario: Known and unknown model
- GIVEN usage for a priced model and for an unpriced model in one window
- WHEN costed
- THEN the priced cost is within 0.01 USD of the hand calculation, the unpriced share reports `cost: null` with its tokens still counted, and the window total equals the priced share with `cost_partial: true`

#### Scenario: 1-hour cache tier
- GIVEN an entry with `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`
- WHEN costed
- THEN each tier uses its own rate

### Requirement: Incremental, non-blocking reads

The reader MUST keep per-file byte offsets and read only appended data on refresh, and MUST NOT block the asyncio event loop. A shrunken or replaced file SHALL be re-read from the start. A partial trailing line MUST be deferred to the next pass, not dropped.

#### Scenario: Append between passes
- GIVEN a completed pass and a file with 2 new lines appended
- WHEN refreshed
- THEN only the new lines are parsed and totals increase by exactly their usage

#### Scenario: No history
- GIVEN `~/.claude/projects` does not exist
- WHEN refreshed
- THEN the result is empty and no error is raised

### Requirement: Read-only

The reader MUST NOT write to, move, or delete anything under `~/.claude/`.
