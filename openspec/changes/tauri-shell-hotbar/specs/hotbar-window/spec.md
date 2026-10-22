# Hotbar Window Specification

## Purpose

The Tauri hotbar: a docked, always-on-top bar. Windows is the only verified platform. Hotbar-owned state lives in `~/.clawd-tank/hotbar-state.json`; user config in `~/.clawd-tank/hotbar.json` (see hotbar-custom-cells).

## Requirements

### Requirement: Placement and persistence

The bar MUST default to the right edge of the primary monitor's usable area, vertically centred with a small margin, be draggable across monitors, and save `{x, y, collapsed, theme}` to `hotbar-state.json` (debounced on move end and on toggle). A saved position MUST be clamped into the usable area of the monitor containing the bar's centre; if the centre is on no connected monitor, the bar MUST use the default placement on the primary monitor. A corrupt or missing state file MUST yield the default. The hotbar MUST NOT write `hotbar.json`.

#### Scenario: Drag and restart
- GIVEN the bar dragged to monitor 2
- WHEN it restarts
- THEN it appears at the saved position

#### Scenario: Partially off-screen
- GIVEN a saved position extending beyond the screen edge
- WHEN loaded
- THEN the bar is moved fully inside the usable area

#### Scenario: Monitor removed
- GIVEN a saved position whose centre is on a monitor no longer connected
- WHEN loaded
- THEN the bar uses the default placement on the primary monitor

#### Scenario: Corrupt state
- GIVEN an unparseable `hotbar-state.json`
- WHEN loaded
- THEN defaults apply and no crash occurs

### Requirement: Collapse

The bar MUST collapse to a small pill on the nearer screen edge (chevron plus per-agent dots, see hotbar-usage-panel Collapsed state) and expand again, via the chevron or the menu, and persist the collapsed state.

#### Scenario: Collapse
- GIVEN an expanded bar
- WHEN collapsed via the chevron or the menu
- THEN only the pill remains, and it stays collapsed after restart

### Requirement: Right-click menu

The menu MUST offer edit config, light/dark, collapse and reload config, and MUST NOT offer autostart or quit. Light/dark MUST persist in `hotbar-state.json`.

The dock's settings button MUST open the same menu.

#### Scenario: Menu items
- GIVEN a right-click on the bar, or a click on its settings button
- WHEN the menu opens
- THEN exactly those four items appear and no quit item exists

#### Scenario: Theme persists
- GIVEN dark theme chosen
- WHEN the hotbar restarts
- THEN dark theme is applied

### Requirement: Single instance

A second launch MUST NOT create a second bar; it MUST show and focus the existing one and exit.

#### Scenario: Second launch
- GIVEN a running hotbar
- WHEN a second instance starts
- THEN the first window is focused and the second process exits

### Requirement: Exit with parent

When `CLAWDY_PARENT_PID` is set, the hotbar MUST exit when that process ends, without busy polling on Windows. If the parent process cannot be opened at startup, the hotbar MUST exit immediately. When the variable is unset (dev mode), no watchdog runs and the hotbar MUST NOT self-terminate.

#### Scenario: Tray killed
- GIVEN the hotbar started with a parent PID
- WHEN the parent process dies
- THEN the hotbar exits

#### Scenario: Parent already gone
- GIVEN `CLAWDY_PARENT_PID` names a nonexistent process
- WHEN the hotbar starts
- THEN it exits immediately

#### Scenario: No parent PID
- GIVEN `CLAWDY_PARENT_PID` unset
- WHEN the hotbar runs
- THEN it keeps running
