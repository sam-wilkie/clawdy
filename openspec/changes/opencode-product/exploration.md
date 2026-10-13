# Exploration: OpenCode desktop pet integration

Status: draft · Artifact store: openspec + engram · Engram: `sdd/opencode-product/explore` (id 3543)

## Goal

Add OpenCode as a supported AI product in the Margarita Tank desktop pet, mirroring the existing Codex and Kiro integration. OpenCode is the AI coding assistant developed by MiniMax (not a Claude Code fork). Approach: an OpenCode plugin that forwards lifecycle events to the daemon socket.

---

## Current State

### Product Architecture (Codex + Kiro)

**Daemon (`daemon.py`)**:
- `SESSION_AGENT_PREFIXES` (line 172-175): `("codex:", "codex")`, `("kiro:", "kiro")`. This is the ONLY place product identity is defined.
- `_session_agent(session_id)` (line 178-183): string-prefix-based product detection — no enum, no type.
- `_aggregate_products()` (line 208-253): collapses per-slot state into `products[]` entries: `{agent, count, anim, bg?, exhausted?}`.
- `_compute_display_state()` (line 734-793): builds the v2 `set_sessions` payload with `anims[]`, `ids[]`, `agents[]`, `products[]`, `subagents`.
- `_set_sessions_payload_for()` (line 830-852): strips `agents`/`products` fields for non-sim transports (BLE MTU constraint). Desktop pet (`sim`) gets them.
- `TOOL_ANIMATION_MAP` (line 37-49): maps daemon tool names → animation names.

**Translator pattern** (`codex_protocol.py`, `kiro_protocol.py`):
- Both mirror `protocol.hook_payload_to_daemon_message()` — same output schema.
- Prefix session IDs: `CODEX_SESSION_PREFIX = "codex:"`, `KIRO_SESSION_PREFIX = "kiro:"`.
- `pid = None` for both (no long-lived PID to track).
- Events translated 1-to-1 using the SAME daemon message schema.

**Renderer** (`desktop/main.js`, `desktop/renderer/renderer.js`):
- `AGENT_ORDER = ["claude", "codex", "kiro"]` — stable display order.
- `AGENT_LABELS = { claude: "Claude", codex: "Codex", kiro: "Kiro" }` — human-readable names.
- `CODEX_STATES`: per-state art override using `assets/codex/cloud-<state>-v2.svg` files.
- Unknown agents fall through to the default `claude` crab (no dedicated art).
- Desktop pet uses `window.pet.agent` (set per-window at creation) to know which product it represents.

**Menus** (`rumps_view.py`, `windows_tray.py`):
- Both have "Install Kiro Hooks (choose folder)..." entry.
- Neither has any OpenCode-specific menu entry.

**PID resolver** (`pid_resolver.py`):
- `_CLAUDE_EXE_NAME = "claude.exe"` — only recognizes Claude Code.
- Does NOT handle `opencode.exe` or any OpenCode process name.

---

## 1. Existing Product Architecture (Codex + Kiro)

### Protocol Translators

Both `codex_protocol.py` and `kiro_protocol.py` implement the SAME interface:
```python
def codex_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]
def kiro_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]
```

Input: raw product hook payload (dict with `hook_event_name`, `session_id`, `cwd`, `tool_name`, etc.)
Output: daemon message dict with `event`, `session_id` (namespaced), `project`, `pid`, etc.

Key patterns:
1. **Session ID namespacing**: `"codex:" + session_id` / `"kiro:" + session_id` — keeps products separate.
2. **Tool name aliasing**: maps product tool names → daemon tool vocabulary (`TOOL_ANIMATION_MAP` keys).
3. **Display name**: `CODEX_DISPLAY_NAME = "Codex"`, `KIRO_DISPLAY_NAME = "Kiro"` — used on notification cards.
4. **PID = None**: neither Codex nor Kiro exposes a hostable long-lived PID.
5. **Same event vocabulary**: session_start, tool_use, tool_done, permission, add, dismiss, compact, subagent_start, subagent_stop.

### Daemon Message Schema

```
session_start  → {"event": "session_start", "session_id": "...", "project": "...", "pid": None}
tool_use      → {"event": "tool_use", "session_id": "...", "tool_name": "...", "project": "...", "pid": None}
tool_done     → {"event": "tool_done", "session_id": "...", "tool_name": "...", "project": "...", "pid": None}
permission    → {"event": "permission", "session_id": "...", "tool_name": "...", "wait": True, "tool_summary": "...", "pid": None}
add (Stop)    → {"event": "add", "hook": "Stop", "session_id": "...", "project": DISPLAY_NAME, "message": "Esperando tu respuesta", "pid": None}
dismiss      → {"event": "dismiss", "hook": "UserPromptSubmit|SessionEnd", "session_id": "...", "pid": None}
compact       → {"event": "compact", "session_id": "...", "pid": None}
subagent_*   → {"event": "subagent_start|stop", "session_id": "...", "agent_id": "...", "pid": None}
```

### Socket Transport

The `clawd-tank-notify` script connects to the daemon's Unix socket (POSIX) or loopback TCP (Windows) and sends these messages. The daemon processes them in `_handle_message()` → `_update_session_state()`.

---

## 2. OpenCode Plugin Surface (Verified)

### Plugin API

Package: `@opencode-ai/plugin` v1.17.15

**Plugin entry point**: a TypeScript module exporting `server: Plugin`:
```typescript
type Plugin = (input: PluginInput, options?: PluginOptions) => Promise<Hooks>;
type PluginModule = { id?: string; server: Plugin; tui?: never; };
```

**Plugin input** (`PluginInput`):
```typescript
{
  client: ReturnType<typeof createOpencodeClient>;
  project: Project;
  directory: string;
  worktree: string;
  serverUrl: URL;
  $: BunShell;  // shell for spawning processes
}
```

**Hooks available** (`Hooks` interface):
```typescript
interface Hooks {
  dispose?: () => Promise<void>;
  event?: (input: { event: Event }) => Promise<void>;  // generic event router
  "tool.execute.before"?: (input, output) => Promise<void>;
  "tool.execute.after"?: (input, output) => Promise<void>;
  "permission.ask"?: (input, output) => Promise<void>;
  "chat.message"?: (input, output) => Promise<void>;
  "experimental.session.compacting"?: (input, output) => Promise<void>;
}
```

**Configuration in `opencode.json`**:
```json
{
  "plugin": ["file:///path/to/plugin.js", "npm-package-name"]
}
```

### OpenCode Event Names vs Claude Code Hook Names

| OpenCode hook/event | Claude Code hook | Daemon event |
|---|---|---|
| `session.created` (via `event` hook) | `SessionStart` | `session_start` |
| `session.deleted` (via `event` hook) | `SessionEnd` | `dismiss` |
| `tool.execute.before` | `PreToolUse` | `tool_use` |
| `tool.execute.after` | `PostToolUse` | `tool_done` |
| `permission.ask` | `PermissionRequest` | `permission` |
| `experimental.session.compacting` | `PreCompact` | `compact` |
| (no direct equivalent) | `UserPromptSubmit` | `dismiss` |
| (no direct equivalent) | `SubagentStart/Stop` | `subagent_start/stop` |

**Important gaps**: OpenCode has NO equivalent for `UserPromptSubmit`, `SubagentStart`, `SubagentStop`. OpenCode also does not expose a PID.

### Event type details

The `event` hook receives `Event` which is a union discriminated by `type` field including `EventSessionCreated` (`type: "session.created"`), `EventSessionDeleted`, etc.

`tool.execute.before` input: `{tool: string, sessionID: string, callID: string}` + `output: {args: any}`
`tool.execute.after` input: `{tool: string, sessionID: string, callID: string, args: any}` + `output: {title: string, output: string, metadata: any}`

### Plugin install path

`~/.config/opencode/plugins/clawd-tank-opencode.js`. The `opencode.json` references it as:
```json
"plugin": ["file:///Users/you/.config/opencode/plugins/clawd-tank-opencode.js"]
```

The plugin is a small shim that registers lifecycle hooks and shells out to a Python bridge script (e.g., `~/.clawd-tank/opencode-bridge.py`) with event data as JSON. The Python bridge sends to the daemon socket.

---

## 3. Integration Boundary Analysis

### Where in the daemon does a new product get added?

**Minimum changes in host Python code**:

1. **`host/clawd_tank_daemon/daemon.py`**: Add `("opencode:", "opencode")` to `SESSION_AGENT_PREFIXES` (line 172). That's the ONLY daemon change needed for the product boundary.

2. **`host/clawd_tank_daemon/opencode_protocol.py`** (new file): Mirror `codex_protocol.py`:
   - `OPENCODE_SESSION_PREFIX = "opencode:"`
   - `OPENCODE_DISPLAY_NAME = "OpenCode"` (notification cards)
   - `OPENCODE_TOOL_ALIASES` mapping OpenCode tool names → daemon tool names
   - `opencode_hook_payload_to_daemon_message(hook) -> Optional[dict]`
   - Translates: `session.created` → `session_start`, `session.deleted` → `dismiss`, `tool.execute.before` → `tool_use`, `tool.execute.after` → `tool_done`, `permission.ask` → `permission`, `experimental.session.compacting` → `compact`
   - `pid = None` (same as Codex/Kiro — no PID available)
   - `project` field: OpenCode passes `directory` (workspace path) — derive project name from basename

3. **Daemon startup**: The daemon doesn't need to change — it already accepts socket connections. The OpenCode plugin sends messages through the same socket interface.

### Does OpenCode emit a session ID we can map to our model?

Yes. `tool.execute.before/after` and `session.created` all provide a `sessionID: string`. We namespace it with `"opencode:" + sessionID` exactly as Codex/Kiro do. No new field needed.

### How does the desktop pet distinguish products?

String-based: `products[].agent` field ("claude", "codex", "kiro", "opencode"). Adding "opencode" is safe — it's a new string value that the renderer handles gracefully (falls through to the default clawd art since there's no `codex`-style art override). No enum or type to extend.

**Safe to add**: The renderer already handles unknown agents (they show the default clawd crab). Full integration (dedicated OpenCode art) is optional future work.

### Where would the OpenCode plugin live on disk?

`~/.config/opencode/plugins/clawd-tank-opencode.js` (or `.ts` if OpenCode supports TypeScript plugins directly). The plugin would be a small shim that:
1. Registers lifecycle hooks
2. Shells out to a Python bridge script (e.g., `~/.clawd-tank/opencode-bridge.py`) with the event data as JSON
3. The Python bridge sends to the daemon socket

The Python bridge is a variant of `clawd-tank-notify.py` — same socket client, different event mapping.

### Does `pid_resolver.py` handle `opencode.exe`?

No. `_CLAUDE_EXE_NAME = "claude.exe"` is hardcoded. OpenCode (like Codex/Kiro) sets `pid = None` in its messages, so the daemon uses time-based eviction. No change needed to `pid_resolver.py`.

### Menu items needing new entries

Both `rumps_view.py` and `windows_tray.py` need a new menu item:
- `"Install OpenCode Hooks"` — similar to `"Install Kiro Hooks (choose folder)..."` but for OpenCode

The controller (`controller.py`) would need an `install_opencode_hooks()` method.

### Tests

**Python host tests** (pytest, `host/tests/`):
- `test_opencode_protocol.py` — unit tests for `opencode_protocol.py` (same pattern as `test_codex_protocol.py`, `test_kiro_protocol.py`)
- `test_opencode_integration.py` — integration test (same pattern as `test_codex_integration.py`): feed OpenCode payloads through the translator → daemon state

**OpenCode plugin tests**: Out of `host/` pytest scope. Plugin tests would validate the TypeScript shim sends correct Python-bridge invocations. Located in `desktop/` or a new `opencode-plugin/` directory — not in `host/tests/`.

---

## 4. Risks

1. **OpenCode `session.created` timing**: Unlike Claude Code's `SessionStart` (fires when session begins), OpenCode may fire `session.created` differently (e.g., after first prompt). This could cause a delayed crab appearance. The `kiro_log_watcher` solved a similar problem for Kiro with log-tailing; the same pattern could apply if needed.

2. **No `SubagentStart/Stop`**: OpenCode does not expose subagent lifecycle. The daemon will not track subagents for OpenCode sessions — they'll show as regular single-agent sessions. The `subagent` HUD counter won't reflect OpenCode subagents. This is a known limitation.

3. **No `UserPromptSubmit`**: OpenCode has no prompt-submit event. End-of-turn detection relies on `Stop`/`session.created` and `session.deleted`. This may affect the dismiss/notification card flow.

4. **OpenCode tool name vocabulary unknown**: The `OPENCODE_TOOL_ALIASES` table must be populated with actual OpenCode tool names. Without a live OpenCode session capture, the tool name mapping is incomplete guesswork.

5. **Plugin shell-out reliability**: The OpenCode plugin uses `BunShell` to spawn the Python bridge. If the bridge fails or OpenCode's shell is unavailable, events are silently dropped. The `otel-hooks` project uses `spawnSync` with a 10-second timeout and silent failure handling.

6. **Plugin installation UX**: Unlike Codex (config file) and Kiro (per-workspace JSON), OpenCode plugins require editing `opencode.json` and placing a `.js` file. The user must do this manually.

---

## 5. Recommendation

**Adopt the plugin + Python bridge approach** (same pattern as `kiro_log_watcher` but with direct hook events instead of log polling).

**Minimum viable change (MVP)**:
1. `host/clawd_tank_daemon/opencode_protocol.py` — translator module
2. Add `("opencode:", "opencode")` to `SESSION_AGENT_PREFIXES` in `daemon.py`
3. `desktop/opencode-plugin/clawd-tank-opencode.js` — OpenCode plugin TypeScript shim
4. `~/.clawd-tank/opencode-bridge.py` — Python bridge (variant of `clawd-tank-notify.py`)
5. Add OpenCode to `AGENT_ORDER` in `desktop/main.js` and `AGENT_LABELS` in `desktop/renderer/renderer.js`
6. Add `"Install OpenCode Hooks"` menu items to `rumps_view.py` and `windows_tray.py`
7. Tests: `test_opencode_protocol.py`, `test_opencode_integration.py`

**Do NOT break the LED path**: All changes are additive to the daemon's existing code paths. The BLE transport and firmware are unaffected.

---

## 6. Open Questions for Proposal

1. **OpenCode tool names**: What are the actual tool names OpenCode emits in `tool.execute.before/after`? Need a live session capture or documentation reference before writing `OPENCODE_TOOL_ALIASES`.

2. **`session.created` semantics**: When exactly does OpenCode fire `session.created`? At workspace open? First prompt? Connection? This affects when the crab appears.

3. **Plugin distribution**: Published npm package (`clawd-tank-opencode`) or local file reference in `opencode.json`? Local file is simpler for development; npm package is cleaner for distribution.

4. **Menu vs auto-install**: Should the menu item "Install OpenCode Hooks" copy the plugin file + edit `opencode.json`, or provide instructions? Editing `opencode.json` programmatically requires parsing/editing JSON.

5. **Idle animation**: What should OpenCode show when idle? Default to the `idle` clawd animation (no OpenCode-specific art for MVP).

---

## Ready for Proposal

**Yes.** The architecture is clear: translator module + namespaced session IDs + daemon socket client. The existing Codex/Kiro integrations provide exact templates. The only meaningful unknowns are OpenCode's specific tool name vocabulary and the exact timing of `session.created` — these should be resolved in the proposal phase with a live capture or documentation lookup.

The renderer, menus, and PID resolver are all minimally invasive changes. The BLE/LED path is completely unaffected.
