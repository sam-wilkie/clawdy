# OpenCode Usage Reader Specification

## Purpose

Read-only per-project aggregation of OpenCode token usage and agent-reported cost (`cost_kind` `reported`) from its local SQLite database (`~/.local/share/opencode/opencode.db`). Windows, project key and exclusion rule are identical to the Claude reader. The source is the legacy `message` table; the newer `session_v2`/`session_message` tables and per-step `part` rows are not read.

## Requirements

### Requirement: Aggregation from assistant messages

The reader MUST total input, output, cache-read and cache-write tokens and the stored cost from assistant messages, per project key (from the message's working directory) and window (today, 7d, 30d, month, by creation time in local timezone). Non-assistant rows MUST be ignored. Cost SHALL be the stored value, never estimated. Rows are re-aggregated fully on each pass over a bounded recent period (62 days), because a row is updated in place when it completes; a completed row MUST NOT be counted twice. Sessions in temp dirs, relative paths or outside a git repo MUST be excluded.

#### Scenario: Fixture totals
- GIVEN a fixture DB with assistant and user rows in two repos
- WHEN aggregated
- THEN per-project totals and cost equal the hand sums of assistant rows only

#### Scenario: Row updated between passes
- GIVEN a pass, then an assistant row's tokens and cost updated in place
- WHEN refreshed
- THEN totals reflect the updated row exactly once

#### Scenario: Cost reported
- GIVEN assistant rows with `cost` values
- WHEN aggregated
- THEN the window cost is their sum, and `cost_kind` is `reported`

### Requirement: Non-blocking read-only access

The reader MUST open the database read-only with a short busy timeout, MUST NOT write, create WAL/SHM files or checkpoints, MUST NOT modify the DB file, and MUST NOT block the running OpenCode app or the event loop.

#### Scenario: Concurrent writer
- GIVEN OpenCode holds a write transaction
- WHEN refreshed
- THEN the reader returns within its timeout and the app is unaffected

### Requirement: Error keeps last snapshot

If the DB is locked, mid-migration, lacks the expected table or column, or a query fails, the reader MUST keep and return the previous snapshot, report status `error`, log once per distinct failure, and retry on the next refresh. Malformed JSON in a row SHALL skip that row.

#### Scenario: Locked after a good pass
- GIVEN one successful pass and then a locked DB
- WHEN refreshed
- THEN the previous snapshot is returned unchanged with status `error`

#### Scenario: Missing table
- GIVEN a DB without the `message` table after a good pass
- WHEN refreshed
- THEN status is `error`, the last snapshot is kept, and nothing is raised

#### Scenario: Error on first pass
- GIVEN no previous snapshot and a locked DB
- WHEN refreshed
- THEN the result is empty with status `error` and no exception escapes

#### Scenario: Absent
- GIVEN the DB file does not exist
- WHEN refreshed
- THEN the result is empty with status `absent` for OpenCode
