# Proposal: Add OpenCode as a desktop pet product

## Intent

Add OpenCode (MiniMax's AI coding assistant) as a fourth product in the Margarita Tank desktop pet, mirroring the existing Codex and Kiro integrations. An OpenCode plugin shells out to a Python bridge that sends lifecycle events to the daemon over the existing socket. The BLE/LED path is unaffected.

---

## Locked Decisions

The following 4 decisions from the prior proposal question round are now **locked and final**:

| # | Decision | Locked Default |
|---|---|---|
| 1 | **Plugin bundling** | NO npm package. Ship as `host/opencode-plugin/clawd-tank-opencode.js` (plain JS/TS). Copy to `~/.config/opencode/plugins/clawd-tank.js` via `install_opencode_hooks()`. If OpenCode's runtime requires `@opencode-ai/plugin` as a peer dependency, declare it in a minimal `host/opencode-plugin/package.json` (user runs `npm install` once). Bundled as data by `host/setup.py` `DATA_FILES` and `host/windows/margarita_tank.spec` `datas`, the same way the other bundled plugin assets ship. |
| 2 | **`OPENCODE_TOOL_ALIASES`** | DEFERRED to spec phase. Declare alias map shape now; stub unknown tools as `passthrough` until live data is captured. TODO: populate from OpenCode docs/source + live session capture in spec phase. |
| 3 | **Notification card message** | GENERIC — same as Codex/Kiro. The crab animation differs per product; card text does NOT change. Per-product flavor is separate future work. |
| 4 | **macOS menu item** | STATELESS install/uninstall. No path prompts. Convention: `~/.config/opencode/opencode.json` (config) + `~/.config/opencode/plugins/clawd-tank.js` (plugin). Enable: backup + merge plugin into `opencode.json` plugin list + copy plugin source. Disable: restore backup. `are_opencode_hooks_installed()` mirrors Codex/Kiro pattern. No interactive UI beyond enable/disable. |

---

## Scope

### In Scope
- `host/clawd_tank_daemon/opencode_protocol.py` — event translator (mirrors `codex_protocol.py`, `kiro_protocol.py`)
- `SESSION_AGENT_PREFIXES` in `daemon.py` — add `("opencode:", "opencode")`
- `~/.clawd-tank/opencode-bridge.py` — Python bridge (stdlib-only, like `clawd-tank-notify.py`)
- `host/opencode-plugin/clawd-tank-opencode.js` — OpenCode plugin (plain JS; bundled to install path)
- `host/opencode-plugin/package.json` — minimal peerDependency declaration for `@opencode-ai/plugin` if required
- `install_opencode_hooks()` in `hooks.py` — stateless install/uninstall; no path prompts
- Menu items in `rumps_view.py` / `windows_tray.py`: "Install OpenCode Hooks" (enable/disable)
- `AGENT_ORDER` in `desktop/main.js` + `AGENT_LABELS` in `desktop/renderer/renderer.js`
- Bundle plugin in `host/setup.py` `DATA_FILES` and `host/windows/margarita_tank.spec` `datas`
- Tests: `test_opencode_protocol.py`, `test_opencode_integration.py`, `test_opencode_hooks_install.py`

### Out of Scope
- OpenCode-specific crab art (falls through to default clawd; future work)
- Subagent tracking (OpenCode emits no `SubagentStart/Stop`)
- PID tracking (`pid = None`, same as Codex/Kiro)
- BLE / firmware changes
- npm package distribution of the plugin as a published package

---

## Capabilities

### New Capabilities
- `opencode-integration`: OpenCode plugin + Python bridge + daemon translator that forwards OpenCode lifecycle events (`session.created/deleted`, `tool.execute.before/after`, `permission.ask`, `session.compacting`) to the daemon socket as first-class product sessions.

### Modified Capabilities
- None at the spec level (daemon `SESSION_AGENT_PREFIXES` addition is an implementation detail, not a spec-level behavior change).

---

## Approach

### Integration shape: OpenCode plugin + Python bridge

OpenCode's plugin API (`@opencode-ai/plugin` v1.17.15) provides lifecycle hooks via a TypeScript module exporting `server: Plugin`. Plugins are registered in `opencode.json` as `"plugin": ["file:///path/to/plugin.js"]`. This is the correct integration surface — tool registration alone cannot capture `session.created/deleted` or `session.compacting`.

The plugin shim (`clawd-tank-opencode.js`) is plain JavaScript (not TypeScript compilation output), copied to `~/.config/opencode/plugins/clawd-tank.js` by the installer. It registers all lifecycle hooks and shells out to `opencode-bridge.py` via `BunShell` with `spawnSync` timeout + silent failure (matching `otel-hooks` pattern).

### Event mapping

| OpenCode hook | Daemon event |
|---|---|
| `event: session.created` | `session_start` |
| `event: session.deleted` | `dismiss` |
| `tool.execute.before` | `tool_use` |
| `tool.execute.after` | `tool_done` |
| `permission.ask` | `permission` |
| `experimental.session.compacting` | `compact` |

`pid = None`. OpenCode has **no** `UserPromptSubmit`, `SubagentStart`, `SubagentStop`.

### `OPENCODE_TOOL_ALIASES` (stubbed for spec phase)

```python
OPENCODE_TOOL_ALIASES = {
    # TODO [spec-phase]: Populate from OpenCode docs + live capture.
    # Stub: unknown tools → "passthrough" (maps to "typing" animation).
    # Once live data is captured, replace stub with empirical mapping.
}
```

The map shape (tool name → daemon animation key) is declared now; values are populated empirically in the spec phase.

### Desktop pet animation

OpenCode sessions show the default clawd animations — no OpenCode-specific art in MVP. The `subagent` HUD counter does not apply.

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `host/clawd_tank_daemon/opencode_protocol.py` | New | Translator: OpenCode events → daemon messages |
| `host/clawd_tank_daemon/daemon.py` | Modified | Add `("opencode:", "opencode")` to `SESSION_AGENT_PREFIXES` |
| `host/opencode-plugin/clawd-tank-opencode.js` | New | Plugin shim (plain JS; bundled by installer) |
| `host/opencode-plugin/package.json` | New | Minimal peerDependency for `@opencode-ai/plugin` |
| `host/clawd_tank_menubar/hooks.py` | Modified | `install_opencode_hooks()`, `uninstall_opencode_hooks()`, `are_opencode_hooks_installed()`; stateless, no path prompts |
| `host/clawd_tank_menubar/rumps_view.py` | Modified | "Install OpenCode Hooks" menu item (enable/disable) |
| `host/clawd_tank_menubar/windows_tray.py` | Modified | "Install OpenCode Hooks" menu item (enable/disable) |
| `host/clawd_tank_menubar/controller.py` | Modified | Calls `install_opencode_hooks()` |
| `host/setup.py` | Modified | `DATA_FILES` bundles `opencode-plugin/` to `~/.config/opencode/plugins/` |
| `host/windows/margarita_tank.spec` | Modified | `datas` bundles plugin for PyInstaller |
| `desktop/main.js` | Modified | Add `"opencode"` to `AGENT_ORDER` |
| `desktop/renderer/renderer.js` | Modified | Add `opencode: "OpenCode"` to `AGENT_LABELS` |
| `~/.clawd-tank/opencode-bridge.py` | New (installed) | Python bridge; not in repo, generated by installer |
| `~/.config/opencode/plugins/clawd-tank.js` | New (installed) | Plugin shim copy target; not in repo |
| `host/tests/test_opencode_protocol.py` | New | Unit tests for `opencode_protocol.py` |
| `host/tests/test_opencode_integration.py` | New | Integration: payload → daemon state |
| `host/tests/test_opencode_hooks_install.py` | New | Hook install/uninstall/merge/remove tests |

**Unchanged**: `firmware/`, `simulator/` (shares `scene.c` with firmware — no new animations), `tools/`, `pid_resolver.py`, BLE/LED path.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `OPENCODE_TOOL_ALIASES` stub → poor animation quality until live capture | Med | Stub as `passthrough` (→ `typing`); spec phase populates from live data; not a release blocker |
| `session.created` fires after first prompt (delayed crab) | Med | Similar to Kiro log-watcher timing; document as known limitation |
| Plugin shell-out failure drops events silently | Low | `spawnSync` with timeout; log to `~/.clawd-tank/clawd-tank.log` |
| Editing `opencode.json` corrupts user config | Low | Atomic read-modify-write; backup before editing; restore on uninstall |
| No `UserPromptSubmit` → end-of-turn differs from Claude | Med | `Stop` + `session.deleted` handle end-of-turn; generic card message |

---

## Rollback Plan

1. `controller.uninstall_opencode_hooks()` — removes plugin entry from `opencode.json`, restores backup, deletes `~/.config/opencode/plugins/clawd-tank.js`, deletes `~/.clawd-tank/opencode-bridge.py`.
2. Daemon continues running; existing OpenCode sessions evict on staleness timeout.
3. No persistent migration state; `products[]` naturally stops showing `"opencode"`.
4. Desktop pet falls back to default clawd art for any lingering OpenCode sessions.

---

## Dependencies

- OpenCode desktop app installed (`opencode.ai`)
- `@opencode-ai/plugin` as peer dependency (declared in `host/opencode-plugin/package.json`; user runs `npm install` once)
- Daemon socket path unchanged (`~/.clawd-tank/sock` POSIX, `~/.clawd-tank/endpoint.json` Windows)

---

## Success Criteria

- [ ] `opencode_protocol.py` translates all 6 OpenCode event types correctly (unit tested)
- [ ] Daemon accepts OpenCode-prefixed session messages and renders crab in desktop pet
- [ ] `install_opencode_hooks()` backs up `opencode.json`, merges plugin, copies shim — stateless, no prompts
- [ ] `uninstall_opencode_hooks()` restores backup and removes all installed artifacts cleanly
- [ ] `are_opencode_hooks_installed()` returns correct state (mirrors Codex/Kiro pattern)
- [ ] Plugin shim shells out to bridge; bridge tests validate socket delivery
- [ ] No regression in existing Codex/Kiro/Claude integrations

---

## Open Questions (Resolved by Locked Defaults)

| Question | Resolution |
|---|---|
| Plugin distribution (npm vs file) | Plain JS file at `host/opencode-plugin/clawd-tank-opencode.js`; peerDependency declared in `package.json` |
| `OPENCODE_TOOL_ALIASES` population | DEFERRED to spec phase; stub with `passthrough`; TODO marker added |
| Notification card message per product | GENERIC — same as Codex/Kiro; per-product flavor is future work |
| macOS menu item UX | STATELESS enable/disable; no path prompts; convention-based paths |

---

**Ready for Spec: Yes.** All four open questions are resolved by the locked defaults above. The two remaining uncertainties — exact `OPENCODE_TOOL_ALIASES` values and precise `opencode.json` plugin schema field name(s) — are spec-phase work: the alias map shape is declared now with a stub, and the plugin schema will be validated against the actual OpenCode plugin runtime during spec writing.
