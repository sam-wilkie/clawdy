# Hotbar Usage Panel Specification

## Purpose

Agent cells (Claude, Codex, OpenCode, Pi) and the side panel that shows usage from `project-usage.json`.

## Requirements

### Requirement: Agent cells and panel

The bar MUST show one cell per agent listed in `hotbar.json` `agents`. Clicking a cell MUST open a panel on the left of the bar, or on the right when the left lacks room, aligned with the bar's top and clamped to the work area; the bar MUST NOT move. The panel MUST hide when it loses focus. It MUST open on Today and offer Today/7d/30d/month, showing output tokens and cost overall (`totals`) and per project, rows sorted by output tokens.

#### Scenario: Open panel
- GIVEN the bar docked on the right edge
- WHEN the Codex cell is clicked
- THEN a panel opens to the left on Today and the bar position is unchanged

#### Scenario: No room on left
- GIVEN the bar near the left edge
- WHEN a cell is clicked
- THEN the panel opens on the right

#### Scenario: Blur
- GIVEN an open panel
- WHEN focus moves elsewhere
- THEN the panel hides

#### Scenario: Switch window
- GIVEN an open panel
- WHEN 7d is selected
- THEN overall and per-project figures show the 7d values

### Requirement: Cost display

Cost display follows `cost_kind`. `reported` (Pi, OpenCode) MUST show `$X`. `estimated` (Claude, Codex) MUST show `~$X (API-equiv.)`. A `null` cost MUST show `no price data`. A `cost_partial` figure MUST be marked as partial.

#### Scenario: Reported
- GIVEN OpenCode `cost_kind` `reported` and cost 1.5
- WHEN rendered
- THEN `$1.50` appears with no `~` or API-equiv. label

#### Scenario: Estimated
- GIVEN Claude `cost_kind` `estimated` and cost 2.0
- WHEN rendered
- THEN `~$2.00 (API-equiv.)` appears

#### Scenario: Unpriced model
- GIVEN a project with cost `null`
- WHEN rendered
- THEN `no price data` appears and its tokens are still shown

### Requirement: Stale, missing, absent and error states

The hotbar MUST poll the file's mtime. `stale` applies when `now - generated_at` exceeds `stale_after_s` from `hotbar.json` (default 300 s); the UI MUST show the age. `missing` applies when the file does not exist or is invalid on first read. A malformed file after a good read MUST keep the last good data. Per agent: `absent` MUST show "not installed", and `error` MUST show an error marker while still showing the kept data.

#### Scenario: Stale
- GIVEN `generated_at` 6 minutes ago and the default threshold
- WHEN rendered
- THEN a stale indicator and the age appear

#### Scenario: Custom threshold
- GIVEN `stale_after_s` 600 and `generated_at` 6 minutes ago
- WHEN rendered
- THEN the data is not stale

#### Scenario: Missing file
- GIVEN no usage file
- WHEN the hotbar starts
- THEN a no-data state shows and no error dialog appears

#### Scenario: Absent agent
- GIVEN `agents.pi.status` is `absent`
- WHEN the Pi cell is opened
- THEN "not installed" is shown instead of zero totals

#### Scenario: Error agent
- GIVEN `agents.opencode.status` is `error` with kept totals
- WHEN the OpenCode cell is opened
- THEN the kept totals show with an error marker

#### Scenario: Refresh
- GIVEN an open panel
- WHEN the file is replaced with new data
- THEN the panel updates without reopening
