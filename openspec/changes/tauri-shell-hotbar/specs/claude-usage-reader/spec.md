# Delta for Claude Usage Reader

Base: `openspec/changes/tauri-shell-hotbar-migration/specs/claude-usage-reader/spec.md` (Change 1, not yet archived). Only the requirement below changes. The shared exclusion rule is implemented once in the shared project-key code and applies to every agent reader.

## MODIFIED Requirements

### Requirement: Per-project aggregation

The reader MUST total input, output, cache-creation and cache-read tokens per project key, for windows today, last 7 days, last 30 days and calendar month. The project key SHALL be the git root of `cwd`; a `cwd` that is non-git, relative, nonexistent or in a temp directory has no project key. The label SHALL be the key's basename. One shared function MUST compute the key. Subfolders of one repo MUST merge into one project. Entries whose `cwd` is inside a temp directory, or outside any git repo, or a relative `cwd`, MUST be excluded from all totals. A temp directory is one under the OS temp location, compared case-insensitively on resolved paths.
(Previously: a `cwd` in a temp dir or outside a git repo fell back to `cwd` and was counted as its own project.)

#### Scenario: Fixture totals
- GIVEN a fixture jsonl with 3 assistant entries in one repo
- WHEN the reader aggregates
- THEN token totals equal the hand-computed sums per window

#### Scenario: Monorepo subfolders
- GIVEN entries with `cwd` `repo/a` and `repo/b` (same git root)
- WHEN aggregated
- THEN `repo` is one project

#### Scenario: Excluded sessions
- GIVEN entries with `cwd` in a temp dir and in a non-git folder, plus one in a git repo
- WHEN aggregated
- THEN only the git repo project appears and no total includes the excluded entries
