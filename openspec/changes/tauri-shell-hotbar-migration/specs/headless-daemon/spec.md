# Headless Daemon Specification

## Purpose

`python -m clawd_tank_daemon.daemon` (there is no package `__main__`) currently parses only `--sim`, `--sim-only`, `--sim-port` (`daemon.py:1674-1690`); preferences and hook install run only in the tray controller. Headless start SHALL reach parity.

## Requirements

### Requirement: Apply preferences on start

Headless start MUST load `~/.clawd-tank/preferences.json` with the existing loader (`preferences.py:21`) and apply `ble_enabled`, `sim_enabled` and `sim_desk_mode` (sets `desktop_pet` on the simulator transport). `enable_opencode` keeps its existing daemon-side handling. `sim_window_visible` and `sim_always_on_top` SHALL be ignored headless (they control a simulator process only the tray spawns). Explicit CLI flags (`--sim`, `--sim-only`, `--sim-port`) MUST override `ble_enabled`/`sim_enabled`. A missing, unparseable or non-object file MUST yield defaults, never a crash, and MUST NOT be overwritten at startup.

#### Scenario: Missing or invalid file
- GIVEN preferences.json is absent, contains `{not json`, or contains `[1]`
- WHEN the daemon starts headless
- THEN it starts with `DEFAULTS` and the file is unchanged

#### Scenario: BLE disabled
- GIVEN `{"ble_enabled": false}`
- WHEN started headless
- THEN no BLE transport is created

#### Scenario: Simulator from preferences
- GIVEN `{"sim_enabled": true}` and no CLI flags
- WHEN started headless
- THEN the simulator transport is enabled on the default port

#### Scenario: Flag precedence
- GIVEN `sim_enabled: false` and `--sim` on the command line
- WHEN started
- THEN the simulator transport is enabled

### Requirement: Hook install on start

Headless start SHALL install or update Claude Code hooks via `hooks.ensure_hooks_current()` only after it acquires the daemon lock, and MUST skip this when `--no-install-hooks` is passed. The legacy autostart in `host/clawd-tank-notify` MUST pass `--no-install-hooks`; the tray remains the hook owner when it runs. Install MUST be idempotent: running it while the tray also runs, or twice in a row, yields a byte-identical `settings.json` with no duplicate groups. An unparseable `settings.json` MUST be left untouched (existing behavior, `hooks.py:1987-1993`) and MUST NOT abort startup.

#### Scenario: Tray and headless both run
- GIVEN hooks installed by the tray, and the tray running or the daemon autostarted by the notify script
- WHEN a headless daemon starts
- THEN settings.json is unchanged

#### Scenario: Opt-out and corrupt settings
- GIVEN `--no-install-hooks`, or a corrupt settings.json
- WHEN the daemon starts
- THEN settings.json is not modified and the daemon runs

### Requirement: Non-regression

Startup MUST NOT touch other tools' hooks, change `~/.clawd-tank/` paths, the launchd label, the macOS bundle id, BLE client, bleak pin, or GATT UUIDs. `--uninstall-hooks` behavior MUST be unchanged. Autostart is out of scope and MUST NOT be added.

#### Scenario: Existing flags
- GIVEN `--sim-only --sim-port 12345`
- WHEN started
- THEN behavior equals today's
