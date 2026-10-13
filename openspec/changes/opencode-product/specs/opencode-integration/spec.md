# Delta for opencode-integration

## Purpose

Add OpenCode (MiniMax AI coding assistant) as a fourth desktop-pet product, mirroring the existing Codex and Kiro integration. An OpenCode plugin shells out to a Python bridge that sends lifecycle events to the daemon over the existing socket. The BLE/LED path is unaffected.

## ADDED Requirements

### Requirement: AC-INSTALL-1 — Fresh macOS plugin install

`controller.install_opencode_hooks()` SHALL, on a fresh macOS host with no prior installation, copy `clawd-tank-opencode.js` from the bundled plugin source path to `~/.config/opencode/plugins/clawd-tank.js`, back up `~/.config/opencode/opencode.json` to `~/.config/opencode/opencode.json.clawd-tank.bak`, and merge a plugin entry into `opencode.json`'s `"plugin"` array pointing to `file:///Users/{user}/.config/opencode/plugins/clawd-tank.js`.

#### Scenario: Fresh macOS install

- GIVEN a macOS host with OpenCode installed, `~/.config/opencode/opencode.json` present, and no prior clawd-tank plugin
- WHEN `controller.install_opencode_hooks()` is called
- THEN `~/.config/opencode/plugins/clawd-tank.js` SHALL exist and contain the bundled plugin shim
- AND `~/.config/opencode/opencode.json` SHALL contain `"clawd-tank.js"` in its `"plugin"` array
- AND `~/.config/opencode/opencode.json.clawd-tank.bak` SHALL be created as a backup of the original

### Requirement: AC-INSTALL-2 — Fresh Windows plugin install

On Windows, `controller.install_opencode_hooks()` SHALL copy the plugin to `%APPDATA%\opencode\plugins\clawd-tank.js`, back up `%APPDATA%\opencode\opencode.json`, and merge the plugin entry.

#### Scenario: Fresh Windows install

- GIVEN a Windows host with OpenCode installed and no prior clawd-tank plugin
- WHEN `controller.install_opencode_hooks()` is called
- THEN `%APPDATA%\opencode\plugins\clawd-tank.js` SHALL exist
- AND `%APPDATA%\opencode\opencode.json` SHALL contain a plugin entry pointing to the local file path
- AND the original SHALL be backed up to `%APPDATA%\opencode\opencode.json.clawd-tank.bak`

### Requirement: AC-INSTALL-3 — Refuse install when opencode.json absent

`install_opencode_hooks()` SHALL return a structured error and NOT create the plugin file when `opencode.json` does not exist.

#### Scenario: Missing opencode.json

- GIVEN `opencode.json` does not exist at the conventional path
- WHEN `install_opencode_hooks()` is called
- THEN it SHALL return a structured error with code `OPENCODE_NOT_INSTALLED`
- AND `~/.config/opencode/plugins/clawd-tank.js` SHALL NOT be created

### Requirement: AC-INSTALL-4 — Idempotent install

A second call to `install_opencode_hooks()` when the plugin is already installed SHALL be a no-op; `are_opencode_hooks_installed()` SHALL return `True` and no files SHALL be modified.

#### Scenario: Idempotent install

- GIVEN the plugin is already installed (`~/.config/opencode/plugins/clawd-tank.js` exists and `opencode.json` has the plugin entry)
- WHEN `install_opencode_hooks()` is called again
- THEN it SHALL return success without modifying any files
- AND `are_opencode_hooks_installed()` SHALL return `True`

### Requirement: AC-UNINSTALL-1 — Clean uninstall

`controller.uninstall_opencode_hooks()` SHALL remove `~/.config/opencode/plugins/clawd-tank.js`, restore `opencode.json` from the backup, and delete the backup.

#### Scenario: Uninstall removes plugin

- GIVEN the plugin is installed and `~/.config/opencode/opencode.json.clawd-tank.bak` exists
- WHEN `controller.uninstall_opencode_hooks()` is called
- THEN `~/.config/opencode/plugins/clawd-tank.js` SHALL NOT exist
- AND `~/.config/opencode/opencode.json` SHALL be restored from the backup
- AND the backup file SHALL be deleted

### Requirement: AC-UNINSTALL-2 — Uninstall when never installed

`uninstall_opencode_hooks()` SHALL be a no-op when the plugin was never installed and SHALL NOT raise.

#### Scenario: Uninstall no-op

- GIVEN the plugin is not installed (`~/.config/opencode/plugins/clawd-tank.js` absent)
- WHEN `uninstall_opencode_hooks()` is called
- THEN it SHALL return success without raising an exception

### Requirement: AC-PLUGIN-1 — Plugin sends session events to daemon socket

When the OpenCode plugin receives a lifecycle event, it SHALL POST a JSON message to the daemon socket (Unix socket on POSIX, authenticated loopback TCP on Windows) at the path exported by `CLAWD_TANK_SOCKET` or `~/.clawd-tank/{sock,endpoint.json}`. The message format SHALL match `codex_hook_payload_to_daemon_message` output schema.

#### Scenario: Plugin sends session.created

- GIVEN the OpenCode plugin is loaded and a session is created in OpenCode
- WHEN `session.created` fires
- THEN the plugin SHALL invoke the Python bridge with a JSON payload
- AND the bridge SHALL deliver a `session_start` message to the daemon socket
- AND the message SHALL have `session_id` prefixed with `"opencode:"`

### Requirement: AC-PLUGIN-2 — Plugin swallows socket errors

When the daemon socket is unreachable, the plugin SHALL swallow the error (not crash OpenCode), MAY retry once with a 500ms back-off, and SHALL NOT block the OpenCode UI.

#### Scenario: Socket unreachable

- GIVEN the daemon is not running and the plugin attempts to send
- WHEN a socket write fails
- THEN the plugin SHALL NOT raise an unhandled exception to OpenCode
- AND the plugin MAY retry once after a 500ms delay
- AND after the retry fails, the event SHALL be dropped silently

### Requirement: AC-PLUGIN-3 — Tool aliases via OPENCODE_TOOL_ALIASES

`OPENCODE_TOOL_ALIASES` SHALL be a dict mapping OpenCode tool names to daemon animation keys. Unknown tools SHALL map to `"passthrough"`. The dict SHALL be stubbed with an empty `{}` and a `TODO` marker; tests MAY mutate it to populate empirical mappings.

#### Scenario: Unknown tool falls through to passthrough

- GIVEN `OPENCODE_TOOL_ALIASES = {}` (empty, stubbed)
- WHEN the plugin sends a `tool.execute.before` with an unknown tool name `"FooTool"`
- THEN the daemon message SHALL contain `tool_name: "passthrough"`
- AND `passthrough` SHALL resolve to the `"typing"` animation

### Requirement: AC-DAEMON-1 — Daemon handles opencode: prefixed sessions

The daemon SHALL create and manage sessions keyed by `"opencode:" + session_id` identically to `"codex:"` and `"kiro:"` sessions. `SESSION_AGENT_PREFIXES` SHALL include `("opencode:", "opencode")`. `_compute_display_state()` SHALL treat OpenCode sessions the same as Claude Code sessions.

#### Scenario: OpenCode session lifecycle

- GIVEN an OpenCode plugin message arrives with `session_id: "abc123"` prefixed as `"opencode:abc123"`
- WHEN the daemon processes `session_start`
- THEN the session SHALL be stored in `dict[session_id → state]` keyed by `"opencode:abc123"`
- AND `_compute_display_state()` SHALL include it in `set_sessions` with `agent: "opencode"`

### Requirement: AC-DAEMON-2 — Staleness eviction for OpenCode sessions

OpenCode sessions SHALL be evicted by the staleness timeout identically to Claude Code sessions. There is no OpenCode-specific staleness exemption.

#### Scenario: OpenCode session evicted on staleness

- GIVEN an OpenCode session has had no events for longer than the staleness timeout
- WHEN the staleness checker runs
- THEN the session SHALL be evicted from `dict[session_id → state]`
- AND no OpenCode-specific exemption SHALL apply

### Requirement: AC-DAEMON-3 — OpenCode appears in products list

When `_aggregate_products()` builds the `products[]` list, OpenCode sessions SHALL appear with `agent: "opencode"` and `product: "opencode"`.

#### Scenario: OpenCode in products array

- GIVEN an active OpenCode session exists
- WHEN `_aggregate_products()` runs
- THEN the `products[]` entry for that session SHALL have `"agent": "opencode"`
- AND `"product": "opencode"` SHALL appear in the desktop pet transport payload

### Requirement: AC-PET-1 — Anim-map resolves OpenCode animation

`anim-map.js` SHALL resolve OpenCode session states (`idle`, `working`, `thinking`, `waiting`, `error`) to valid sprite animation names using the same state-mapping logic as Codex/Kiro.

#### Scenario: OpenCode working state maps to BUILDING

- GIVEN an OpenCode session is in `working` state
- WHEN the renderer calls `anim-map.js` for the OpenCode slot
- THEN the returned animation SHALL be `"BUILDING"` (or the equivalent working-tier animation)

### Requirement: AC-PET-2 — Graceful degradation for unknown product

When the renderer receives a `products[]` entry with an unknown `agent` value, it SHALL fall through to the default clawd animation without error.

#### Scenario: Unknown product falls through

- GIVEN a `products[]` entry has `agent: "opencode"` but the renderer has no explicit OpenCode mapping
- WHEN the renderer processes the entry
- THEN it SHALL render the default clawd crab animation
- AND no error SHALL be thrown

### Requirement: AC-PET-3 — AGENT_ORDER includes opencode

`AGENT_ORDER` in `desktop/main.js` SHALL include `"opencode"` in the same position as Codex and Kiro. `AGENT_LABELS` SHALL include `opencode: "OpenCode"`.

#### Scenario: OpenCode appears in agent ordering

- GIVEN `AGENT_ORDER` contains `"opencode"`
- WHEN the desktop pet renders multiple agent slots
- THEN OpenCode sessions SHALL appear in the correct position relative to Codex and Kiro

### Requirement: AC-UI-1 — macOS menu Install OpenCode Hooks

The macOS menu bar app SHALL have an "Install OpenCode Hooks" menu item that calls `controller.install_opencode_hooks()` and reports success/failure via the standard status pattern (mirroring Codex/Kiro).

#### Scenario: macOS menu install

- GIVEN the macOS menu bar app is running
- WHEN the user clicks "Install OpenCode Hooks"
- THEN `controller.install_opencode_hooks()` SHALL be invoked
- AND the result SHALL be reported via the standard status notification pattern

### Requirement: AC-UI-2 — Windows tray Install OpenCode Hooks

`windows_tray.py` SHALL add the same "Install OpenCode Hooks" menu item.

#### Scenario: Windows tray install

- GIVEN the Windows tray app is running
- WHEN the user clicks "Install OpenCode Hooks"
- THEN `controller.install_opencode_hooks()` SHALL be invoked
- AND the result SHALL be reported via the standard status notification pattern

### Requirement: AC-UI-3 — enable_opencode=false ignores OpenCode sessions

When `enable_opencode` preference is `False`, the daemon SHALL ignore arriving OpenCode plugin messages (same pattern as `enable_codex: False`).

#### Scenario: OpenCode disabled

- GIVEN `enable_opencode` is `False` in daemon preferences
- WHEN an OpenCode plugin message arrives
- THEN the daemon SHALL NOT create or update any session
- AND the message SHALL be silently discarded

### Requirement: AC-TEST-1 — opencode_protocol.py unit tests

`host/tests/test_opencode_protocol.py` SHALL exist with at minimum: 3+ payload parsing test cases covering `session.created → session_start`, `session.deleted → dismiss`, `tool.execute.before → tool_use`, and one integration test covering the full session lifecycle: registered → working → idle → evicted.

#### Scenario: Protocol translation tests

- GIVEN `test_opencode_protocol.py` with cases for all 6 event types
- WHEN `pytest` runs
- THEN all test cases SHALL pass
- AND `session.created` SHALL translate to `session_start` with prefixed session_id
- AND `session.deleted` SHALL translate to `dismiss`

### Requirement: AC-TEST-2 — Hook install/uninstall tests

`host/tests/test_opencode_hooks_install.py` SHALL mirror `test_codex_hooks_install.py` with: install/uninstall round-trip, idempotency, missing-opencode-json error, and Windows path tests with mocked `Path.home()`.

#### Scenario: Install/uninstall round-trip

- GIVEN a temporary directory with a mock `opencode.json`
- WHEN `install_opencode_hooks()` is called then `uninstall_opencode_hooks()` is called
- THEN the original `opencode.json` SHALL be restored byte-for-byte
- AND the plugin file SHALL be absent

### Requirement: AC-TEST-3 — Plugin JS tests

`host/opencode-plugin/tests/` SHALL contain a vitest or `node:test` test file that: mocks the socket write call and verifies it is called with correct JSON, verifies error swallowing on socket failure, and verifies retry-once-with-500ms-backoff behavior.

#### Scenario: Plugin sends correct JSON

- GIVEN the plugin has a mocked socket client
- WHEN `session.created` event fires
- THEN the socket write SHALL be called with a JSON string containing `event: "session_start"` and `session_id` prefixed with `"opencode:"`

### Requirement: AC-BUNDLE-1 — macOS bundle includes plugin

`host/setup.py` `DATA_FILES` SHALL include `opencode-plugin/` bundled to a path from which `hooks.resolve_plugin_source()` returns a valid filesystem path.

#### Scenario: Plugin source resolvable in bundle

- GIVEN a packaged macOS `.app` build
- WHEN `hooks.resolve_plugin_source()` is called
- THEN it SHALL return a valid path to `clawd-tank-opencode.js` inside the bundle
- AND `install_opencode_hooks()` SHALL be able to copy from that path

### Requirement: AC-BUNDLE-2 — Windows bundle includes plugin

`host/windows/margarita_tank.spec` `datas` SHALL include the `opencode-plugin/` directory so `hooks.resolve_plugin_source()` returns a valid path after PyInstaller bundles.

#### Scenario: Plugin source resolvable in Windows bundle

- GIVEN a packaged Windows `MargaritaTank/` directory from PyInstaller
- WHEN `hooks.resolve_plugin_source()` is called
- THEN it SHALL return a valid path to `clawd-tank-opencode.js` inside that directory

## Out of Scope

- LED device animations for OpenCode-specific states (BLE/LED path is shared, not product-specific)
- Subagent lifecycle tracking for OpenCode (OpenCode does not expose `SubagentStart`/`SubagentStop`)
- npm publishing of the plugin (`peerDependency` model only; user runs `npm install` once; no `npm publish`)
- OpenCode-specific notification card copy (generic card text, same as Codex/Kiro)
