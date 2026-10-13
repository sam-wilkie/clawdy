# Design: Add OpenCode as a desktop pet product (4th agent)

## Technical Approach

Add OpenCode as a fourth prefixed-session product in the Margarita Tank, mirroring the existing `codex:`/`kiro:` pair. The integration surface is **a Node plugin that shells out to a Python bridge over the existing daemon socket** — no daemon protocol changes, no BLE/firmware/simulator touches, no new animation enum. The plugin lives at `host/opencode-plugin/clawd-tank-opencode.js`, copies itself to `~/.config/opencode/plugins/clawd-tank.js` via a stateless installer in `host/clawd_tank_menubar/hooks.py`, and at runtime spawns `~/.clawd-tank/opencode-bridge.py` (a 1-shot stdlib Python, same family as `clawd-tank-notify`) for every lifecycle event. The bridge reuses the daemon socket (Unix on POSIX, loopback TCP via `endpoint.json` on Windows) and the daemon's existing `_handle_message()` pipeline.

Strict TDD on. Tests land **first** per capability (`test_opencode_protocol.py`, `test_opencode_hooks_install.py`, `test_opencode_integration.py`) plus a separate `host/opencode-plugin/tests/` for the JS shim. No firmware or simulator code is touched — `simulator/shims/` is irrelevant because nothing in `scene.c`, `ble_service.c`, or `notification_ui.c` changes.

## Component Diagram

```
   OpenCode TUI / CLI
           |
           | loads plugin (opencode.json "plugin": ["file:///.../clawd-tank.js"])
           v
   clawd-tank-opencode.js   (host/opencode-plugin/, plain JS, no build)
           |
           | $`bun:bash spawnSync`  (timeout 5s, silent on error)
           v
   opencode-bridge.py       (host/clawd_tank_menubar/hooks.py installs this to
           |                 ~/.clawd-tank/opencode-bridge.py; stdlib only,
           |                 mirrors clawd-tank-notify)
           |
           | Unix socket (POSIX) / loopback TCP+token (Windows) — same socket
           | the daemon already listens on; message shape = same as the daemon's
           | existing _handle_message() contract
           v
   daemon _handle_message() ──► _session_states[session_id]
                                       |
                                       v
                                _compute_display_state()
                                products[] now includes:
                                   {"agent":"opencode", "count":N, "anim":A}
                                       |
                  ┌────────────────────┴────────────────────┐
                  v                                         v
        set_sessions ─► BLE/ESP32-C6                  set_sessions ─► desktop pet
        (anims/ids only — MTU-safe, agent                (full payload incl. products[],
         prefix is irrelevant to firmware)                agents[]) → renderer.js
                                                                   │
                                                                   v
                                                            AGENT_ORDER picks slot,
                                                            AGENT_LABELS["opencode"]
                                                            = "OpenCode", crab falls
                                                            through to default art
```

## Module-by-Module Design

### `host/clawd_tank_daemon/opencode_protocol.py` (NEW — mirrors `codex_protocol.py` line-for-line)

- **Responsibility**: Translate OpenCode plugin hook payloads to daemon messages.
- **Public API**:
  - `OPENCODE_SESSION_PREFIX = "opencode:"` (str const)
  - `OPENCODE_DISPLAY_NAME = "OpenCode"` (str const; fixed notification-card project name)
  - `OPENCODE_TOOL_ALIASES: dict` — **declared but empty `{}`** with `# TODO[spec-phase]: populate from OpenCode docs + live capture`; unknown tools fall through to `"passthrough"` (resolved by the daemon's `_tool_to_anim` as `typing`).
  - `def opencode_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]`
- **Event mapping** (definitive):

  | OpenCode input shape | Translator branch | Daemon event |
  |---|---|---|
  | `{"type":"session.created", sessionID, directory}` | namespaced `session_start` | `session_start` |
  | `{"type":"session.deleted", sessionID}` | namespaced `dismiss` | `dismiss` (no card — mirrors `SessionEnd`) |
  | `tool.execute.before {tool, sessionID, callID}` | `tool_use` | `tool_use` |
  | `tool.execute.after {tool, sessionID, callID, args}` | `tool_done` | `tool_done` |
  | `permission.ask {tool, sessionID}` (analogous to Claude's `PermissionRequest`) | `permission` with `wait=True` and `tool_summary` | `permission` |
  | `experimental.session.compacting {sessionID}` | `compact` | `compact` |
- **Key invariants**:
  - `session_id = OPENCODE_SESSION_PREFIX + raw_session_id` always; raw id never leaks to `daemon._handle_message()`.
  - `pid = None` always (OpenCode has no hostable PID; daemon uses no-PID staleness timeout).
  - All outputs are valid `_handle_message()` payloads (same schema as Codex/Kiro).
- **Test surface**: `host/tests/test_opencode_protocol.py` — 3 unit cases plus 1 lifecycle case (per AC-TEST-1): translate each of the 6 events; assert `session_id` is prefixed; assert `pid is None`; assert `tool_name == "passthrough"` for unknown tools when `OPENCODE_TOOL_ALIASES = {}`; multi-event lifecycle produces the registered → working → idle → evicted sequence.

### `host/clawd_tank_daemon/__init__.py` — `opencode_hook_payload_to_daemon_message` export

- Add the import + `__all__` entry parallel to the existing codex/kiro exports.
- Test surface: existing import-only tests via `tests/test_opencode_integration.py`.

### `host/clawd_tank_daemon/daemon.py` — `SESSION_AGENT_PREFIXES` + display-state thread

- Add `("opencode:", "opencode")` as the third tuple in `SESSION_AGENT_PREFIXES` (currently `("codex:", "codex")`, `("kiro:", "kiro")`).
- **No code changes** required in `_compute_display_state()`, `_aggregate_products()`, `_session_agent()`, or `_set_sessions_payload_for()` — all of them already key off `_session_agent(session_id)` (which becomes `"opencode"` for any prefixed session id) and already emit the full payload to the `"sim"` (desktop pet) transport while stripping agents/products for everything else. OpenCode appears in `products[]` automatically.
- Key invariant: the **only** place product identity is decided is the prefix tuple; this preserves the architecture rule from the exploration.
- Test surface: extended `tests/test_session_state.py::test_*` (or new `test_opencode_integration.py`) — same shape as `_add_session(d, "kiro:...")` cases but with `"opencode:abc"`; assert `state["agents"]` contains `"opencode"`, products list contains `{"agent":"opencode", ...}`, and staleness eviction (default `NO_PID_STALENESS_TIMEOUT` already applies because `pid is None`).

### `host/clawd_tank_menubar/hooks.py` — installer suite

- Add **one** `resolve_plugin_source(frozen, executable, resourcepath, module_file) -> Path` — same shape as `resolve_mod_source()` at line 1628 but returning `base / "opencode-plugin"`. Single helper, used by both `install_opencode_hooks()` (read source) and the runtime fallback (debug logs).
- Add constants: `OPENCODE_CONFIG_DIR`, `OPENCODE_CONFIG_PATH`, `OPENCODE_PLUGIN_DIR`, `OPENCODE_PLUGIN_FILENAME = "clawd-tank.js"`, `OPENCODE_PLUGIN_BACKUP_SUFFIX = ".clawd-tank.bak"`. Paths computed from `Path.home()` / `%APPDATA%` per platform (matches the `CLAWD_DIR` convention at line 25).
- Add `OPENCODE_BRIDGE_SCRIPT: str` (`textwrap.dedent`-ed, stdlib-only, mirrors `NOTIFY_SCRIPT`); one CLI argument `"opencode"`; reads JSON from `argv[1]`, writes the corresponding daemon message to the socket (function body closely copies `NOTIFY_SCRIPT`'s `main()`).
- Add helpers + 3 public functions (`install_opencode_hooks`, `uninstall_opencode_hooks`, `are_opencode_hooks_installed`) — see "Plugin ↔ Daemon message contract" for behaviour.
- Key invariants:
  1. **`opencode.json` is the source of truth** for installation; not editing `~/.config/opencode/opencode.json` at all leaves the file untouched. The backup file is the user's original.
  2. **Idempotency** — re-running `install_opencode_hooks()` with the entry already present does not rewrite files.
  3. **Ownership principle** — only entries whose value equals our plugin path are removed by `uninstall_opencode_hooks()`; other users' plugin entries are preserved.
  4. **`install_opencode_hooks()` refuses** when `opencode.json` is missing (returns a structured error with code `OPENCODE_NOT_INSTALLED`, per AC-INSTALL-3) and **also refuses** when the file is unparseable JSON (leaves it byte-for-byte intact — same rule the Kiro/Codex installers already follow).
- Test surface: `host/tests/test_opencode_hooks_install.py` (mirrors `test_codex_hooks_install.py` structure): fresh install, idempotency, missing-config error, unparseable JSON refused, uninstall round-trip restores from backup, **install/uninstall round-trip restores `opencode.json` byte-for-byte**, wrong platform path tests under mocked `Path.home()` + `sys.platform`.

### `~/.clawd-tank/opencode-bridge.py` (NEW at runtime — generated by `install_opencode_hooks`)

- Same source as `OPENCODE_BRIDGE_SCRIPT` (textwrap string in `hooks.py`, written via `NOTIFY_SCRIPT.write_text` pattern). Drop-in cousin of `clawd-tank-notify`: reads one JSON payload from `argv[1]`, looks up `CLAWD_TANK_SOCKET` (POSIX: `~/.clawd-tank/sock`) or falls back to `~/.clawd-tank/endpoint.json` (Windows), writes the daemon message, exits 0.
- The translator runs **inside the bridge** (a tiny ~30-line dict-of-closures, exact port of `codex_hook_payload_to_daemon_message`) so we don't spawn a Python interpreter per event to import the daemon's translator. Stdlib only.
- Test surface: extend `host/tests/test_notify_standalone.py` with one bridge case or create `tests/test_opencode_bridge.py` — mirror `test_notify_script_matches_protocol_converter` pattern.

### `host/opencode-plugin/clawd-tank-opencode.js` (NEW — plain JS, no build, no `tsc`)

- **Responsibility**: thin lifecycle hook → JSON event → `spawnSync` to the bridge.
- **Public surface** (CommonJS for OpenCode's Bun runtime):
  - `module.exports = { server: async (input, opts) => ({ ...hooks }) }` — `server` only (no `tui`).
  - Hooks implemented: `event` (router for `session.created`/`session.deleted`), `tool.execute.before`, `tool.execute.after`, `permission.ask`, `experimental.session.compacting`. All other hooks: NOT IMPLEMENTED (OpenCode silently no-ops unused hooks).
  - `BRIDGE_PATH = "<path-derived-at-runtime>"` — at install time the JS file uses a hardcoded absolute path injected by `install_opencode_hooks()` (string replace of one sentinel token), or at first import it self-locates via `__filename` siblings + `os.homedir()`. **Decision deferred to sdd-tasks** (see Open Questions).
- **Key invariants**:
  1. Socket write failures **never** throw into OpenCode — `try/catch` wraps the `spawnSync`; on failure the JS MAY do one retry with `setTimeout(..., 500)` (per spec AC-PLUGIN-2), then swallows.
  2. Plugin returns successfully even if the bridge is missing — never blocks OpenCode's TUI.
  3. JSON shape invariant: `{ event, session_id, project, tool_name?, wait?, tool_summary?, pid: null, ... }` — same schema the daemon consumes.
- **Test surface**: `host/opencode-plugin/tests/test_plugin.test.mjs` (using `node:test`). Mocks `Bun.spawnSync` (or whatever BunShell API is canonical for the version OpenCode 1.17 ships with — see Open Question 2). Covers: (a) `session.created` → expected JSON with `event:"session_start"` and `session_id` prefixed `"opencode:"`; (b) socket-down does not throw; (c) optional retry-once-with-500ms-backoff is exercised.

### `host/opencode-plugin/package.json` (NEW — minimal)

- Single `{"name":"clawd-tank-opencode","private":true,"peerDependencies":{"@opencode-ai/plugin":"^1.17.15"}}`. NOT published (no `repository`/`publishConfig` keys). Sits next to the JS shim so OpenCode's plugin loader recognises it as a directory plugin (or is ignored — OpenCode's file-vs-folder convention is the Open Question 2 below).

### `host/opencode-plugin/tests/` (NEW — node:test or vitest)

- One test file `test_plugin.test.mjs` per spec AC-TEST-3.
- Lives under `host/opencode-plugin/tests/`, NOT under `host/tests/` (pytest does not run them and node is not a host dependency — mirrors how `desktop/` keeps its own renderer tests).

### `host/setup.py` + `host/windows/margarita_tank.spec` — bundle entries

- **`setup.py`**: append `("opencode-plugin", ["opencode-plugin/clawd-tank-opencode.js", "opencode-plugin/package.json"])` to `DATA_FILES`. Tuple shape is `(destination folder, [source paths relative to `host/`])` — the same shape every other bundled asset uses.
- **`margarita_tank.spec`**: append `(os.path.join(REPO_ROOT, "host", "opencode-plugin", "clawd-tank-opencode.js"), "opencode-plugin")` + same for `package.json` to the `datas=[...]` list at line 90.
- **Add `host/tests/test_opencode_plugin_packaging.py`** asserting:
  1. `host/opencode-plugin/clawd-tank-opencode.js` exists at repo root.
  2. `setup.py` lists `"opencode-plugin"` and the JS path.
  3. `margarita_tank.spec` lists the JS path under `datas`.
  4. `release.yml` includes the assertion (next section).

### `.github/workflows/release.yml` — bundle-presence guard

- Under "Check the bundled Claude Code mod" (macOS, line 107-111) append a parallel block `"Check the bundled OpenCode plugin"` testing `host/dist/Margarita Tank.app/Contents/Resources/opencode-plugin/clawd-tank-opencode.js`.
- Under Windows "Check the build" (line 207-214) the existing `for f in ...` loop MUST include the JS file in the `for f in ...` list (it currently lists `.exe` + the simulator + the icon; we add `opencode-plugin/clawd-tank-opencode.js`). Note: the build-check blocks assert a bundled file exists under `Resources/` — copy that shape for the opencode plugin.

### `host/clawd_tank_menubar/controller.py` — `install_opencode_hooks()` action

- Public method **stateless** (no folder prompt — Kiro needs a folder because its hooks are per-workspace; OpenCode hooks are global, so we mirror Codex's no-prompt UX). Calls `hooks.install_notify_script()` first (so the bridge can find the daemon), then `hooks.install_opencode_hooks()`, then reports success/failure via the same `self._view.alert(...)` pattern as `install_hooks()` (line 449-482). No controller-level preferences — the **menu's checked/unchecked state is queried via `hooks.are_opencode_hooks_installed()`** at `_render()` time.

### `host/clawd_tank_menubar/rumps_view.py` + `windows_tray.py` — menu item

- Add `self._opencode_hooks_item = rumps.MenuItem("Install OpenCode Hooks", callback=...)` (or pystray equivalent) BELOW `_kiro_hooks_item` (rumps line 170; windows line 152).
- `_opencode_hooks_item.state = hooks.are_opencode_hooks_installed()` — re-evaluated in `_render()`. Reflects the real disk state, NOT an internal controller flag.

### `desktop/main.js` — `AGENT_ORDER`

- Single-line change: `const AGENT_ORDER = ["claude", "codex", "kiro", "opencode"];`. `orderedAgents()` already places unknown agents at the end with `ia === -1 ? 99 : ia`, so the existing sort Just Works.

### `desktop/renderer/renderer.js` + `renderer/dashboard.js` — labels

- `AGENT_LABELS.opencode = "OpenCode"` (line 20) — replaces the `AGENT` label text when the window was spawned for the opencode slot (`window.pet.agent === "opencode"`).
- **No per-state art override** — `ART_STATES` stays `AGENT === "codex" ? CODEX_STATES : STATES`; opencode falls through to the default Clawd STATES table (per proposal locked decision #3 — no OpenCode-specific art).
- `AGENT_NAMES` in `dashboard.js` (line 8) gets the same `opencode: "OpenCode"` entry.

### `desktop/renderer/anim-map.js` — **NO CODE CHANGES NEEDED**

- `mapAnim(name, bg, conductMs, exhausted)` is product-agnostic. The proposal/spec phrase "alias passthrough + no-bg for no-subagent" is already the existing behaviour:
  - **passthrough**: any unknown `name` falls through to `name || "idle"` (line 45) — OpenCode will pass through whatever animation the daemon computed for the session, untouched.
  - **no-bg**: with `pid=None` and no subagents, `_aggregate_products()` never sets `bg` on the OpenCode entry (it omits the key), so `bg === 0` here, and the function returns the daemon name unchanged. **The "opencode" branch is implicit because the function does not enumerate products.**
- Test surface: existing `desktop/renderer/tests/test_anim-map.js` already covers the `bg=0, name="..."` passthrough — extend one parametrized case to assert that a product=opencode session with `bg=0` and any daemon anim maps to itself.

## Plugin ↔ Daemon Message Contract

### Final JSON wire format (plugin → daemon socket)

The bridge accepts a single JSON object on `argv[1]` (one payload per spawn). Top-level keys:

| Field | Required | Source in OpenCode hook | Notes |
|---|---|---|---|
| `event` | yes | `hook_event_name` or `event.type` mapping (see table below) | literal `session_start` / `tool_use` / `tool_done` / `permission` / `dismiss` / `compact` — daemon vocabulary |
| `session_id` | yes | `${OPENCODE_SESSION_PREFIX}${raw}` | ALWAYS prefixed; bridge does the namespacing (not the plugin) so the plugin shim stays dumb |
| `project` | yes (some events), absent on others | `directory` basename (mirrors `cwd` in Codex/Kiro) | omitted entirely on `dismiss`/`compact` |
| `tool_name` | tool events only | `_opencode_tool_name(raw)` | unknown tools → `"passthrough"` |
| `pid` | always `null` | hardcoded | matches Codex/Kiro |
| `wait` | `permission` events only, `true` | hardcoded | matches Claude `PermissionRequest` |
| `tool_summary` | `permission` events only | `permission_tool_summary(tool_name, args)` (reuse `protocol.permission_tool_summary`; same import the Codex/Kiro translators use) | first N chars per protocol helper |
| `source` | `session_start` events only | passthrough of optional metadata | mirrors Codex/Kiro |

Event-type mapping (bridge is the single translator, identical to `opencode_protocol.py`):

| Bridge input `event` | Daemon field | OpenCode hook that emits it |
|---|---|---|
| `session_start` | from `{"type":"session.created", sessionID, directory}` | plugin `event` hook, EventSessionCreated |
| `dismiss` | from `{"type":"session.deleted", sessionID}` | plugin `event` hook, EventSessionDeleted |
| `tool_use` | from `tool.execute.before` | plugin `tool.execute.before` |
| `tool_done` | from `tool.execute.after` | plugin `tool.execute.after` |
| `permission` | from `permission.ask` (mapped per spec; OpenCode call it `permission.ask` per exploration §2) | plugin `permission.ask` |
| `compact` | from `experimental.session.compacting` | plugin `experimental.session.compacting` |

Unknown event types return `None` and the bridge exits silently (matches Codex/Kiro's behaviour on irrelevant hooks).

**OpenCode-specific quirks** (per spec):
1. **No `UserPromptSubmit`** — end-of-turn detection relies on `Stop` (when OpenCode finishes a turn) + `session.deleted`. The bridge MUST NOT emit a separate `dismiss` for `UserPromptSubmit` because there isn't one to listen for.
2. **No `SubagentStart`/`SubagentStop`** — the `_session_states[session_id]["subagents"]` set stays empty. The HUD's subagent counter simply does not show OpenCode subagents (which do not exist in OpenCode's runtime per exploration §2).
3. **`pid = null`** — never set.
4. **No `agent_id` field** — does not appear in any payload even when the tool ran on behalf of a sub-concept (OpenCode's `tool.execute.before`/`after` shapes do not include `agent_id`).

## Config and Preferences

### New preference key: `enable_opencode`

- **Default `True`**, in `~/.clawd-tank/preferences.json`. Stored alongside `enable_codex`/`enable_kiro` — but **neither of those actually exist today** in the codebase (Codex/Kiro are simply ON when installed; their menu items show installed-ness rather than a preference gate). **The `enable_opencode` preference is genuinely new** per spec AC-UI-3.
- Semantics: when `False`, the daemon's `_handle_message()` discards any message whose `session_id` starts with `opencode:` (same shape as if the plugin weren't installed). Implementation: a `daemon.preferences.get("enable_opencode", True)` check at the top of `_handle_message()`, ahead of `_update_session_state()`.
- **Lockable from the menu** by the user via a new controller method + tray toggle; out of MVP scope (per the "Stateless install/uninstall" locked decision #4 — preferences remain manually edited for MVP).

### Bundle layout

- `clawd-tank-opencode.js` is bundled by both:
  - **macOS (py2app)**: `Contents/Resources/opencode-plugin/clawd-tank-opencode.js` — read at runtime via `hooks.resolve_plugin_source()` which reads `os.environ["RESOURCEPATH"]` (mirrors `resolve_mod_source()`).
  - **Windows (PyInstaller onedir)**: `dist/MargaritaTank/opencode-plugin/clawd-tank-opencode.js` — next to `MargaritaTank.exe`, read via `sys.executable`-relative.
  - **Checkout (dev)**: `<repo>/host/opencode-plugin/clawd-tank-opencode.js` — read via `Path(__file__).parents[2] / "host" / "opencode-plugin" / ...`.
- A **single** `resolve_plugin_source()` helper handles all three (mirror of `resolve_mod_source` at line 1628).

### Backup file naming

`opencode.json.clawd-tank.bak` next to the original — exact convention from spec AC-INSTALL-1 / AC-UNINSTALL-1. Written before the first edit, deleted by `uninstall_opencode_hooks()` after restoring.

## Cross-Platform Differences

| Concern | macOS / Linux | Windows |
|---|---|---|
| Config dir | `~/.config/opencode/` | `%APPDATA%\opencode\` |
| Config file | `~/.config/opencode/opencode.json` | `%APPDATA%\opencode\opencode.json` |
| Plugin dir | `~/.config/opencode/plugins/` | `%APPDATA%\opencode\plugins\` |
| Installed plugin | `~/.config/opencode/plugins/clawd-tank.js` | `%APPDATA%\opencode\plugins\clawd-tank.js` |
| Daemon socket | Unix socket at `~/.clawd-tank/sock` (via `CLAWD_TANK_SOCKET` or `~/.clawd-tank/sock` default) | Loopback TCP via `~/.clawd-tank/endpoint.json` (port + token) |
| `opencode.json` plugin entry pointing at | `file:///Users/{user}/.config/opencode/plugins/clawd-tank.js` | `file:///C:/Users/{user}/AppData/Roaming/opencode/plugins/clawd-tank.js` |
| Code paths differ? | No | Same logic; just a path-layer switch via `sys.platform` or `_is_windows()` (mirrors `CLAWD_DIR` resolution at line 25) |

The **plugin runtime** loads from one fixed directory per platform (per the spec's "verify in spec phase or as follow-up task" note). Both platforms use OpenCode's `opencode.json` with `"plugin": ["file:///..."]` — this is consistent across desktop and CLI builds of OpenCode.

The **bridge runtime** differs only at the socket path layer — the Python bridge already needs to handle both, so this is free thanks to reusing `clawd-tank-notify`'s socket-resolution code.

The **plugin shim** is pure JS with no platform-specific imports — `BunShell` (`$`) abstracts the spawn across macOS/Linux/Windows.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| 1 | **Distribution shape** | Plain JS file (`host/opencode-plugin/clawd-tank-opencode.js`) + minimal `package.json` declaring `@opencode-ai/plugin` as a peerDependency. NO npm publish. | (a) True npm package `clawd-tank-opencode` registered on npm registry; (b) compile the shim from TypeScript at build time (passes through `tsc`) | Mirror the **other bundled-plugin** integrations: same peerDependency shape, same "files-copied-into-target-folder" workflow, same py2app+PyInstaller bundling path (`host/setup.py` `DATA_FILES` and `host/windows/margarita_tank.spec` `datas`, both of which already bundle a sibling plugin this way). Avoids a registry round-trip on first install (npm requires the user has Node + runs `npm install`). An OpenCode install that sees `package.json` will resolve `@opencode-ai/plugin` from the user's existing `node_modules` (OpenCode itself ships with that dep) or fail loudly on the user side. (Mirrors the proposal's locked decision #1 and the existing bundling precedent.) |
| 2 | **Per-prefix session IDs** (`"opencode:"` in the daemon) instead of an enum | `SESSION_AGENT_PREFIXES` tuple, third entry `("opencode:", "opencode")` | (a) Add a new `agent` field on every message; (b) extend the daemon's product enum and require every future protocol update to bump it | String-prefix is the **existing convention** (`codex:`, `kiro:`). It lets the daemon stay schema-strict (`session_id` is the only product marker) and `_session_agent()` works unchanged. Adding a new product is a one-line tuple edit. Spec AC-DAEMON-1 explicitly mandates this. |
| 3 | **OpenCode sessions reuse Claude Code's session-state machine** | `_session_states[session_id]`, same `update_session_state()` paths, same `state_to_anim` resolution, same staleness eviction | (a) Independent `opencode_session_states` dict with a parallel lifecycle; (b) explicit product switch statements | The whole session lifecycle (registered → working → idle → evicted) is identical in OpenCode — the only delta is `pid=None` (which Codex/Kiro already exercise). Reuse means no risk of drift between Claude and OpenCode state semantics; the daemons's display state computation, animation mapping, permission handling, etc. all Just Work. |
| 4 | **`"opencode"` added to `AGENT_ORDER`** in `desktop/main.js` rather than a "generic unknown" branch | Insert as the 4th entry of the existing 3-element list | (a) Detect unknown agents and put them in a fallback position; (b) only put known entries in `AGENT_ORDER`; rely on the existing `-1 → 99` fallback | The existing array already handles unknown agents at the end via the `indexOf === -1 ? 99 : ia` sort comparator. Adding `"opencode"` simply gives it a defined position (rightmost), which is what the user wants visually. No new code path needed. The desktop pet **renderer** needs to know "opencode" by name (for the label and dashboard), but the **window manager** only needs it for display order. |
| 5 | **Notification card message is generic** | Card text uses fixed `OPENCODE_DISPLAY_NAME = "OpenCode"` only on `Stop` (mirrors Codex/Kiro `add` with Stop hook); other events dismiss clean. The actual card body content matches Codex/Kiro's "Esperando tu respuesta" | (a) Custom card copy per product; (b) suppress cards entirely for OpenCode | Mirrors the **proposal's locked decision #3** — per-product card flavor is future work. The crab animation differs per product; the card text does not. This keeps notification UX consistent and avoids three text variants to maintain. |
| 6 | **`OPENCODE_TOOL_ALIASES = {}` (stubbed)** | Empty dict with `# TODO[spec-phase]` marker; unknown tools → `"passthrough"` resolves to `"typing"` anim via daemon | (a) Best-guess mapping from Claude tool names; (b) full upfront enumeration of OpenCode tool names without live data | Per the proposal's locked decision #2: live OpenCode tool name vocabulary is unverified. The empty stub is **safe** (falls through to `passthrough` → `typing`), **observable** (live sessions reveal the real names), **revisable** (extending the dict is a one-file edit once data lands). Spec AC-PLUGIN-3 explicitly mandates this behaviour. |
| 7 | **`enable_opencode` preference** is new (not mirrored from `enable_codex`) | New `preferences.json` key, default `True`, daemon gates `_handle_message()` on it | (a) Mirror Codex/Kiro (no preference gate — installed is installed); (b) per-product toggle stored only in the menu state | Spec AC-UI-3 introduces this preference explicitly. Codex/Kiro never had one (verified by absence in `host/clawd_tank_menubar/` — `enable_codex`/`enable_kiro` do not exist). Adding it only for OpenCode is **intentional**: a user may want to disable OpenCode plugin events without uninstalling the plugin (eg: temporarily debugging). Implementation is minimal — 3 lines in `daemon._handle_message`. Future products can adopt it. |
| 8 | **No device-side changes** (BLE/LED/firmware/simulator all untouched) | Zero diffs in `firmware/`, `simulator/`, `tools/`, `pid_resolver.py` | (a) Add OpenCode-specific animations; (b) reuse `hat_mishap`/`low_battery` for OpenCode errors; (c) BLE payload widening | OpenCode events arrive at the device as positional `anims[]` + `ids[]` after the daemon's existing transport shaping. The product prefix is irrelevant to the firmware. The desktop pet is the only renderer that needs the string for its label/sort, and that's a 2-line `desktop/main.js` + `renderer.js` change. Spec AC-PET-2 explicitly mandates this graceful-degradation behaviour. |
| 9 | **Plugin → bridge transport** | One-shot JSON payload per `spawnSync` invocation, with one optional retry-with-500ms-backoff on socket failure | (a) Long-lived child process with newline-delimited JSON on stdin/stdout; (b) socket write directly from the JS shim (drop the bridge) | (a) is robust but holds one open Python process per OpenCode session lifetime — leaves orphan processes when OpenCode crashes; the explorer explicitly recommends against it. (b) requires the JS shim to know the daemon's socket path/credentials, which differs per platform AND varies per installation (token rotation on Windows); the bridge's job is to encapsulate that. One-shot spawn + silence-on-failure matches the `otel-hooks` reference in the proposal. |

## Risks → Mechanism

| Risk | Likelihood | Mitigation |
|---|---|---|
| **OpenCode plugin schema field name drift** (the verification at exploration §2 looked at one OpenCode version; future versions may rename `tool.execute.before` → `tool.execute` etc.) | Med | (1) The plugin shim is one file — a renaming only touches that file. (2) `host/opencode-plugin/tests/` has per-hook cases; bumping the plugin's `@opencode-ai/plugin` peer dep forces a re-test. (3) `ac-claw`'s verification log will be re-checked at start of `sdd-apply`. **TODO before sdd-tasks**: re-verify the exact hook field names against the running OpenCode version installed on the user's machine. |
| **`OPENCODE_TOOL_ALIASES` is empty** → all tools animate as `typing` until live capture lands | High initially → low after first live capture | (1) Spec AC-PLUGIN-3 explicitly permits empty stub. (2) `event.type` field on `event`-routed events gives us free tool names once OpenCode fires `tool.execute.before` (the more reliable of the two paths). (3) `_tool_to_anim` in daemon falls through to `typing` for `passthrough` — visually coherent, not a crash. (4) Spec phase populates the map empirically. |
| **Concurrent installs across platforms** (user clicks "Install" twice rapidly; macOS install + Windows install both run because the user has the app installed on both machines) | Low | (1) `install_opencode_hooks()` is reentrant-safe — the second call hits the idempotency guard at `are_opencode_hooks_installed()`. (2) Cross-platform is irrelevant (different filesystems, different processes). (3) `_write_json_atomic` serializes the write through a tmp file (same pattern Claude/Codex installers use). |
| **`opencode.json` corruption if write fails mid-merge** | Low | (1) `install_opencode_hooks()` reads → backups → modifies in memory → atomic-writes the tmp file → `os.replace`. (2) `uninstall_opencode_hooks()` restores from backup byte-for-byte. (3) If the file is unparseable JSON, install REFUSES and leaves it untouched (test_case: `test_unparseable_file_left_untouched` in `test_codex_hooks_install.py`). |
| **`session.created` may fire after first prompt** (delayed crab appearance) | Med | (1) Documented as a known limitation in `installer_hooks` UI. (2) Mirrors Kiro's `SessionStart`-via-log-watcher pattern in spirit — `kiro_log_watcher.py` solves the same problem for Kiro. Future enhancement: tail OpenCode's session log for early registration. **Not a release blocker** — the first prompt will still fire `tool.execute.before` and the crab will appear with the working animation. |
| **Plugin shell-out failure drops events silently** (daemon down → `spawnSync` returns non-zero exit) | Low | (1) `spawnSync` has a 5s timeout (`{ timeout: 5000 }`). (2) Bridge exits 0 even on socket failure (mirrors `clawd-tank-notify` exit-0 policy — fire and forget). (3) Plugin swallows every exception; retries once per AC-PLUGIN-2. (4) Bridge writes a single debug line to `~/.clawd-tank/clawd-tank.log` (read by the tray's log viewer) before exiting silently. |
| **`enable_opencode` preference vs installed-ness** divergence (plugin installed but preference is False, or vice versa) | Low | (1) Both states are independently meaningful: installed-but-disabled lets a developer keep the plugin while suppressing events. (2) The menu item's checked state reflects `hooks.are_opencode_hooks_installed()`, not the preference. (3) Documented in installer user-facing strings. |

## Out-of-Scope Reaffirmation

These items are **explicitly NOT** part of this design (per proposal §Scope and spec §Out-of-Scope):

- **OpenCode-specific crab art** (no `assets/opencode/*.svg`; the default `assets/clawd/*.svg` paths in renderer.js render fine). MVP uses the same Clawd art as the Claude window — `AGENT_LABELS.opencode = "OpenCode"` is the only OpenCode string the renderer sees.
- **Subagent lifecycle tracking** (`SubagentStart`/`Stop`) — OpenCode does not emit these. The HUD subagent counter shows 0 for OpenCode sessions.
- **`agent_id` propagation** — OpenCode's `tool.execute.{before,after}` shapes do not include `agent_id`; the bridge omits the field.
- **PID tracking** — `pid = None` exactly like Codex/Kiro.
- **BLE / firmware changes** — zero diffs in `firmware/` or `simulator/`. The `simulator/shims/` indirection is irrelevant because nothing in `scene.c`/`ble_service.c`/`notification_ui.c` changes (the simulator only matters when shared source changes).
- **npm package publish** — `host/opencode-plugin/package.json` has `private: true`, no `repository`, no `publishConfig`. The user runs `npm install` against OpenCode's bundled deps (or, more commonly, has OpenCode's runtime already providing `@opencode-ai/plugin`).
- **OpenCode-specific notification card copy** — generic text identical to Codex/Kiro.
- **Cross-OS opencode config path resolution** beyond `~/.config` (POSIX) / `%APPDATA%` (Windows) — alternative XDG locations are out of scope; OpenCode does not support them as of the verified version.

## Open Questions (for sdd-tasks)

- [ ] **Plugin shim path injection**: hardcode the installed plugin's absolute path into the JS file at install time (string-replace a sentinel token), or have the shim self-locate via `__filename` + `os.homedir()` at runtime? Self-location is more robust against the user reinstalling the bridge at a different path but adds a Node `os`/`path` dependency on the shim. **Defer to sdd-tasks** with whichever wins on first Playwright/OpenCode end-to-end run.
- [ ] **OpenCode plugin file vs folder convention**: when `opencode.json` lists `file:///.../clawd-tank.js` does OpenCode's loader require the file's sibling `package.json` to exist, or is the JS file self-sufficient? Re-verify against `ac-claw`'s running version before sdd-tasks starts. Affects whether `clawd-tank-opencode.js` needs a sibling `package.json` on the TARGET machine (not just the bundled one).
- [ ] **BunShell API for sync spawn with timeout**: exact call shape in Bun 1.x / whatever OpenCode 1.17.15 ships (`spawnSync` vs `Bun.spawnSync` vs `$\`command\``). Re-verify against the running OpenCode before sdd-tasks; the dead-simple fallback is `child_process.execSync` from Node API (which Bun supports) with `{ timeout: 5000 }`.
- [ ] **`@opencode-ai/plugin` peer dep resolution**: if the user has OpenCode installed but `@opencode-ai/plugin` is not findable from `~/.config/opencode/plugins/clawd-tank.js`'s perspective (different `node_modules` resolution root), the plugin may fail. If so: bundle a copy of the type stubs instead. Defer.
