# Pi Usage Reader Specification

## Purpose

Read-only, offline per-project aggregation of Pi (gentle-shell) token usage and agent-reported cost (`cost_kind` `reported`) from `~/.pi/agent/sessions/<dir>/*.jsonl`. Windows, project key and exclusion rule are identical to the Claude reader.

## Requirements

### Requirement: Aggregation from assistant messages

The reader MUST take `cwd` from the file's `session` record and, from each assistant message, input, output, cache-read, cache-write tokens and the reported total cost, attributed by the message timestamp. Cost SHALL be the stored value, never estimated. Non-assistant messages MUST be ignored. A message whose entry `id` was already counted MUST NOT be counted again. Sessions in temp dirs, relative paths or outside a git repo MUST be excluded.

#### Scenario: Fixture totals
- GIVEN a fixture session with 2 assistant messages and 1 user message in one repo
- WHEN aggregated
- THEN tokens and cost equal the sums of the 2 assistant messages, `cost_kind` `reported`

#### Scenario: Missing cost
- GIVEN an assistant message with usage but no cost object
- WHEN aggregated
- THEN its tokens count, its cost contributes nothing, and the window is `cost_partial: true`

#### Scenario: Duplicate entry id
- GIVEN two records with the same entry `id`
- WHEN aggregated
- THEN the usage counts once

### Requirement: Tolerant, incremental, read-only

Unparseable lines, a missing `session` record (file skipped), missing token fields (as 0) and unreadable files MUST be skipped and logged, never aborting the pass. Refresh MUST read only appended data, defer a partial trailing line, re-read a shrunken file and never block the event loop. The reader MUST NOT write under `~/.pi/`.

#### Scenario: Garbage and truncated lines
- GIVEN a file with a garbage line and a truncated last line
- WHEN aggregated, then the line completes and a refresh runs
- THEN valid records count once and the completed line is counted on the second pass

#### Scenario: Absent
- GIVEN `~/.pi/agent/sessions` does not exist
- WHEN refreshed
- THEN the result is empty with status `absent` for Pi, and no error is raised
