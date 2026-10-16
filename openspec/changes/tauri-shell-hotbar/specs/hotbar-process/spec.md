# Hotbar Process Specification

## Purpose

The Python tray owns the hotbar lifetime. There is no hotbar autostart of its own.

## Requirements

### Requirement: Start and stop with the tray

The tray MUST start the hotbar when the daemon starts (if enabled) with `CLAWDY_PARENT_PID` set to its own PID, and MUST stop it on quit, including the force-exit path. `stop()` MUST be idempotent and synchronous. The hotbar and its WebView2 children MUST NOT outlive the tray. Programs the user launched through `run:` cells MUST NOT be killed by stop.

#### Scenario: Normal lifecycle
- GIVEN `hotbar_enabled` true and a fake process factory
- WHEN the tray starts, then quits
- THEN one hotbar is spawned with the parent PID and is stopped on quit

#### Scenario: Stop twice
- GIVEN a stopped hotbar
- WHEN `stop()` is called again
- THEN nothing happens and no error is raised

### Requirement: Stale process cleanup

The hotbar records `{pid, exe}` in `~/.clawd-tank/hotbar.pid`. Before spawning, the tray MUST kill the recorded pid only if that live process's image path equals both the recorded exe and the resolved hotbar exe. A mismatching image path, a dead pid, or a missing or corrupt pidfile MUST NOT kill anything. Cleanup is skipped off Windows.

#### Scenario: Orphan from a crashed tray
- GIVEN a pidfile whose pid is alive with the matching exe path
- WHEN the tray starts
- THEN that process is killed before the new spawn

#### Scenario: Reused pid
- GIVEN a pidfile whose pid is now another program
- WHEN the tray starts
- THEN nothing is killed

### Requirement: Executable lookup

The exe MUST be resolved in order: `CLAWDY_HOTBAR_EXE` (absolute existing file), `clawdy-hotbar` next to `sys.executable`, then `hotbar/src-tauri/target/release/`.

#### Scenario: Env override
- GIVEN `CLAWDY_HOTBAR_EXE` points to an existing file
- WHEN resolving
- THEN that path is used regardless of other locations

### Requirement: Missing exe is non-fatal

If no exe is found, the tray MUST log a warning and continue with daemon and pets unaffected.

#### Scenario: No exe
- GIVEN no candidate exists
- WHEN the tray starts
- THEN a warning is logged, nothing is spawned, and the tray works normally

### Requirement: `hotbar_enabled` toggle

A "Show hotbar" tray checkbox MUST be backed by `hotbar_enabled` (default true) in `preferences.json`, via read-modify-write. Toggling off MUST stop the process; on MUST start it. The value MUST persist across restarts, and a non-object preferences file yields the default.

#### Scenario: Toggle off
- GIVEN a running hotbar
- WHEN the user unchecks "Show hotbar"
- THEN the process stops and `hotbar_enabled` is false on disk

#### Scenario: Disabled at startup
- GIVEN `hotbar_enabled` false
- WHEN the tray starts
- THEN no hotbar is spawned

### Requirement: Headless daemon excluded

The headless daemon MUST NOT launch the hotbar.

#### Scenario: Headless start
- GIVEN `python -m clawd_tank_daemon.daemon`
- WHEN it starts
- THEN no hotbar process is spawned
