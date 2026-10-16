# Hotbar Usage Panel Specification

## Purpose

The agent dock (Claude, Codex, OpenCode, Kiro, Gentle Shell) and the side panel that shows usage and plan limits from `project-usage.json`. UI copy is Spanish; the visual system is the pets' Mochi palette with a derived dark theme.

## Requirements

### Requirement: Agent dock and panel

The bar MUST be a vertical pill dock with, in order: a collapse chevron, one button per agent listed in `hotbar.json` `agents` (default `claude`, `codex`, `opencode`, `kiro`, `pi`), an "all agents" button and a settings button. Each agent button MUST show the agent's monochrome logo (ink in light theme, white in dark) and an accessible label naming the agent and its figures. Clicking an agent button MUST open the panel focused on that agent's card; the "all agents" button MUST open it with every card. The panel MUST open on the left of the bar, or on the right when the left lacks room, aligned with the bar's top and clamped to the work area; the bar MUST NOT move. The panel MUST hide when it loses focus. It MUST open on Today and offer Today/7d/30d/month, showing token figures overall (`totals`) and per project, rows sorted by output tokens, each project with a share bar in the agent's brand colour.

#### Scenario: Open panel
- GIVEN the bar docked on the right edge
- WHEN the Codex button is clicked
- THEN a panel opens to the left on Today showing the Codex card, and the bar position is unchanged

#### Scenario: All agents
- GIVEN the bar docked on the right edge
- WHEN the "all agents" button is clicked
- THEN the panel shows one card per configured agent

#### Scenario: No room on left
- GIVEN the bar near the left edge
- WHEN an agent button is clicked
- THEN the panel opens on the right

#### Scenario: Blur
- GIVEN an open panel
- WHEN focus moves elsewhere
- THEN the panel hides

#### Scenario: Switch window
- GIVEN an open panel
- WHEN 7d is selected
- THEN overall and per-project figures show the 7d values

### Requirement: Agent naming

The agent with id `pi` MUST be displayed as "Gentle Shell" in every hotbar label, tooltip and card. Data ids MUST NOT change.

#### Scenario: Gentle Shell label
- GIVEN `agents.pi` in the usage file
- WHEN the dock and panel render
- THEN the label reads "Gentle Shell" and no "Pi" text appears

### Requirement: Plan-first display

An agent whose entry has `billing` `plan` MUST show its plan limits and MUST NOT show any money figure. Each limit MUST show its name (Spanish, keyed by limit `id`, falling back to `label`), `used_pct` as a bar in the agent's brand colour, and the time until `resets_at`. Codex MUST also show `reset_credits` when it is a number; Kiro MUST show `credits` used, plan limit and remaining. A plan agent with no `ok` plan block MUST show a no-limits note and no money. An entry without `billing` MUST be treated as `payg`.

#### Scenario: Claude on a plan
- GIVEN Claude `billing` `plan` with limits `session` 62 and `weekly` 38
- WHEN its card renders
- THEN both limits show with bars and reset times, and no currency amount appears anywhere for Claude

#### Scenario: Kiro credits
- GIVEN Kiro `plan.credits` `{used: 340, limit: 1000}`
- WHEN its card renders
- THEN 340 used, 1.000 plan and 660 remaining appear, with no token section

#### Scenario: Plan without data
- GIVEN Claude `billing` `plan` and `plan.status` `no_data`
- WHEN rendered
- THEN a no-limits note shows, no ring is drawn, and no money appears

#### Scenario: Old file without billing
- GIVEN a usage file whose agents carry no `billing`
- WHEN rendered
- THEN every agent is shown as pay-as-you-go with its cost

### Requirement: Cost display

Money MUST be shown only for `payg` agents. `reported` cost (OpenCode, Gentle Shell) MUST show the USD amount formatted with `Intl.NumberFormat("es-CO")`. `estimated` cost (Codex with an API key) MUST show the amount prefixed with `≈` and labelled "estimado". A `null` cost MUST show "Sin precio" with tokens still shown. A `cost_partial` figure MUST be marked as partial. The panel header MUST show the summed pay-as-you-go spend for the selected window, prefixed with `≈` when any part is estimated.

#### Scenario: Reported
- GIVEN OpenCode `billing` `payg`, `cost_kind` `reported` and cost 1.5
- WHEN rendered
- THEN the amount 1,50 in USD appears with no `≈` and no "estimado" label

#### Scenario: Estimated
- GIVEN Codex `billing` `payg`, `cost_kind` `estimated` and cost 2.0
- WHEN rendered
- THEN `≈` and the amount 2,00 in USD appear with the "estimado" label

#### Scenario: Unpriced model
- GIVEN a payg project with cost `null`
- WHEN rendered
- THEN "Sin precio" appears and its tokens are still shown

#### Scenario: Plan agent cost hidden
- GIVEN Claude `billing` `plan` with `totals.today.cost` 4.0
- WHEN rendered
- THEN no amount appears for Claude and the header spend excludes it

### Requirement: Dock signal

A plan agent's button MUST draw a ring whose fill is the highest `used_pct` among its limits, stroked in the agent's brand colour, and in cherry when that value is 90 or more. No ring MUST be drawn when `plan` is absent, malformed or not `ok`. A payg agent's button MUST show a small "$" badge. An agent with status `error` MUST show a cherry badge and its label MUST say the read failed. A stale file MUST show a badge on the "all agents" button.

#### Scenario: Ring at warning level
- GIVEN Claude limits 93 and 71
- WHEN the dock renders
- THEN the Claude ring is filled to 93 % in cherry

#### Scenario: Ring in brand colour
- GIVEN Codex limits 21 and 47
- WHEN the dock renders
- THEN the Codex ring is filled to 47 % in the Codex brand colour

#### Scenario: Malformed plan
- GIVEN Kiro `plan.limits` that is not a list
- WHEN the dock renders
- THEN no ring is drawn for Kiro and nothing else changes

#### Scenario: Payg badge
- GIVEN Gentle Shell `billing` `payg`
- WHEN the dock renders
- THEN its button shows the "$" badge and no ring

### Requirement: Collapsed state

When collapsed, the bar MUST show a small pill with the chevron and one dot per configured agent in its brand colour. A dot MUST be dimmed when the agent's highest `used_pct` is below 30, cherry with a halo when it is 90 or more or when the agent status is `error`, and in the track colour when the agent is `absent`. The pill's tooltip and accessible label MUST name the agents needing attention (90 % or more, or `error`).

#### Scenario: Attention tooltip
- GIVEN Claude at 93 % and OpenCode with status `error`
- WHEN the bar is collapsed
- THEN both dots are cherry with a halo and the tooltip names Claude and OpenCode

#### Scenario: Absent dot
- GIVEN `agents.kiro.status` `absent`
- WHEN the bar is collapsed
- THEN the Kiro dot uses the track colour

### Requirement: Agent cards

Each panel card MUST show the agent's idle pet (Claude crab, Codex cloud, Mochi monster for Kiro, OpenCode and Gentle Shell), the agent's original coloured logo beside its name, and a chip naming the billing mode ("Plan", "Pago por uso", or "API · estimado"). The pet MUST be decorative (empty `alt`).

#### Scenario: Codex card
- GIVEN the Codex card
- WHEN rendered
- THEN the cloud pet, the coloured Codex logo and a billing chip appear

### Requirement: Stale, missing, absent and error states

The hotbar MUST poll the file's mtime. `stale` applies when `now - generated_at` exceeds `stale_after_s` from `hotbar.json` (default 300 s); the UI MUST show the age. `missing` applies when the file does not exist or is invalid on first read. A malformed file after a good read MUST keep the last good data. Per agent: `absent` MUST show "No instalado", and `error` MUST show an error marker while still showing the kept data. An agent missing from the file (for example `kiro` from an older daemon) MUST be treated as `absent`.

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
- WHEN the Gentle Shell button is opened
- THEN "No instalado" is shown instead of zero totals

#### Scenario: Agent missing from file
- GIVEN a usage file with no `kiro` entry
- WHEN rendered
- THEN Kiro shows as not installed and the other agents render normally

#### Scenario: Error agent
- GIVEN `agents.opencode.status` is `error` with kept totals
- WHEN the OpenCode button is opened
- THEN the kept totals show with an error marker

#### Scenario: Refresh
- GIVEN an open panel
- WHEN the file is replaced with new data
- THEN the panel updates without reopening
