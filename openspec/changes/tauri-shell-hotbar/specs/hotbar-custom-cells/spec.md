# Hotbar Custom Cells Specification

## Purpose

User-defined cells from `~/.clawd-tank/hotbar.json`, with `open:`, `run:` and `panel:` actions. The config is user-owned and only read by the hotbar; actions are constrained.

## Requirements

### Requirement: Config parsing

The hotbar MUST read `hotbar.json` (`version`, `stale_after_s`, `agents`, `cells` with `id`, `label`, `action`, optional `args`). A missing file MUST be created with defaults; an existing file MUST never be rewritten by the hotbar. An invalid cell MUST render disabled with its error while valid cells still load. A config that fails to parse MUST keep the last good config and show an error badge.

#### Scenario: Missing config
- GIVEN no `hotbar.json`
- WHEN the hotbar starts
- THEN a default file is created and the five agent buttons show (Claude, Codex, OpenCode, Kiro, Gentle Shell)

#### Scenario: Invalid cell
- GIVEN a config with one valid cell and one with an unknown action prefix
- WHEN loaded
- THEN the valid cell works and the invalid one is disabled with its error

#### Scenario: Malformed JSON on reload
- GIVEN a syntax-broken config
- WHEN reload is chosen
- THEN the previous cells stay and an error badge shows

### Requirement: Actions resolved by cell id

The UI MUST invoke a cell by `id` only. The Rust side MUST look the action up in the loaded config; the UI MUST NOT be able to supply a program or command line.

#### Scenario: Unknown id
- GIVEN an invoke with an id not in the config
- WHEN handled
- THEN nothing runs and an error is returned

### Requirement: `open:` action

`open:` MUST accept only `http` and `https` URLs and open them in the default browser. Any other scheme (`file:`, `javascript:`, custom, none) MUST be rejected at config load and at invoke, without opening.

#### Scenario: Allowed
- GIVEN `open:https://example.com`
- WHEN clicked
- THEN the URL opens in the browser

#### Scenario: Rejected scheme
- GIVEN `open:file:///C:/Windows/System32/calc.exe`
- WHEN loaded
- THEN the cell is disabled with an error and nothing opens

### Requirement: `run:` action

`run:` MUST start the program with its `args` list directly, with no shell interpretation, detached with no stdio. Shell metacharacters MUST be passed literally. An empty program or a failing start MUST be reported without crashing.

#### Scenario: No shell
- GIVEN `run:` with an argument `a & calc`
- WHEN clicked
- THEN the argument reaches the program as one literal string

#### Scenario: Detached
- GIVEN a launched program
- WHEN the hotbar exits
- THEN the program keeps running

#### Scenario: Empty program
- GIVEN `run:` with no program
- WHEN loaded
- THEN the cell is disabled with an error

### Requirement: `panel:` action

`panel:` MUST run the command without a shell, show its stdout (UTF-8, lossy) in the panel, kill it after 10 seconds, and cap captured stdout at 64 KiB.

#### Scenario: Timeout
- GIVEN a command that runs longer than 10 s
- WHEN clicked
- THEN it is killed at 10 s and a timeout state is shown

#### Scenario: Output cap
- GIVEN a command printing 200 KiB
- WHEN run
- THEN at most 64 KiB is shown, marked truncated, and the process does not hang

#### Scenario: Non-zero exit
- GIVEN a command that exits non-zero
- WHEN run
- THEN an error state with the exit status is shown
