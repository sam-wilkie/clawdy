# Codex Usage Reader Specification

## Purpose

Read-only, offline per-project aggregation of Codex token usage and estimated cost from `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. The file carries no cost, so cost is estimated from the dated price table (`cost_kind` `estimated`). Windows (local timezone), project key, exclusion rule and tolerant parsing are identical to the Claude reader.

## Requirements

### Requirement: Per-response token aggregation

The reader MUST count tokens only from per-response usage records, deduplicated on `response_id`, and MUST NOT count cumulative running-total records. Fresh input tokens SHALL be input minus cached-input minus cache-write-input; cache-read is the cached count; cache-write is the cache-write count; output is the output count (reasoning is already included in it). Cwd comes from the session's first record. Each response is attributed to the model most recently declared in that session. Totals are per project key and window (today, 7d, 30d, month). Sessions in temp dirs, relative paths or outside a git repo MUST be excluded.

#### Scenario: No double counting
- GIVEN a fixture with 2 per-response records and cumulative token-count records for the same turns
- WHEN aggregated
- THEN totals equal the sum of the 2 per-response records only

#### Scenario: Duplicate response id
- GIVEN the same `response_id` appears twice
- WHEN aggregated
- THEN its usage counts once

#### Scenario: Excluded cwd
- GIVEN one session in a git repo and one in a temp dir
- WHEN aggregated
- THEN only the repo project appears

### Requirement: Estimated cost

Cost MUST come from the dated, sourced price table; only models with a sourced row are priced. A model missing from the table MUST yield `cost: null` for its share (tokens still counted), with window `cost_partial: true`, and `null` when nothing is priced. Never 0, never an exception.

#### Scenario: Priced and unpriced model
- GIVEN responses for a priced model and for an unpriced model
- WHEN costed
- THEN priced cost matches the hand calculation within 0.01 USD, and the window reports `cost_partial: true`

### Requirement: Tolerant, incremental, read-only

Malformed lines, records without usage, missing token fields (as 0) and unreadable files MUST be skipped and logged. Refresh MUST read only appended data, defer a partial trailing line, re-read a shrunken file, keep per-file context (cwd, model) across passes, and never block the event loop. The reader MUST NOT write under `~/.codex/`.

#### Scenario: Garbage line
- GIVEN a file with an unparseable line between two valid records
- WHEN aggregated
- THEN both valid records count and no exception escapes

#### Scenario: Absent
- GIVEN `~/.codex/sessions` does not exist
- WHEN refreshed
- THEN the result is empty with status `absent` for Codex, and no error is raised

#### Scenario: Append keeps context
- GIVEN a completed pass and a response appended later in the same file
- WHEN refreshed
- THEN the new response is attributed to the file's cwd and latest model
