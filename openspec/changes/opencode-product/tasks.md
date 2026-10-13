# Tasks: Add OpenCode as a desktop pet product (4th agent)

> Status (2026-10-13): this planning checklist has not been reconciled with implementation. OpenCode translator, plugin installer, menu wiring, desktop labels and aggregate usage reader exist in the checkout. Unchecked tasks below do not mean absent code or verified delivery. See [current status](../../../docs/clawdy-desktop-estado-2026-10-13.md); runtime and packaging checks remain pending.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~250-350; PR2 ~350-500 (JS plugin + bridge + renderer + protocol tests); PR3 ~100 (bundling + verify) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Daemon-side translator + installer hooks + menu wiring (no OpenCode runtime needed) | PR 1 (base=main) | `cd host && .venv/Scripts/python.exe -m pytest tests/test_opencode_protocol.py tests/test_opencode_hooks_install.py -v` | N/A (unit tests only) | Delete 3 new files + revert daemon.py + hooks.py changes |
| 2 | JS plugin shim + Python bridge + desktop renderer + protocol tests (plugin bundle NOT included) | PR 2 (base=PR1) | `cd host && .venv/Scripts/python.exe -m pytest tests/test_opencode_protocol.py tests/test_opencode_integration.py -v` | N/A (proto + integration tests) | Delete opencode-plugin/, bridge from hooks.py, renderer changes |
| 3 | Bundling (setup.py / spec / release.yml) + manual verify | PR 3 (base=PR2) | `cd host && .venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_ble.py --ignore=tests/test_ble_client.py -x` | `clawd-tank-sim --listen --headless` with TCP connect | Revert DATA_FILES / datas entries |

---

# PR 1 — Daemon translator + installer + menu wiring

## Phase 1: Daemon-side translator

- [ ] 1.1 [TDD-RED] Create `host/tests/test_opencode_protocol.py` with RED test cases: `session.created → session_start` (with `"opencode:"` prefix), `session.deleted → dismiss`, `tool.execute.before → tool_use`, `tool.execute.after → tool_done`, `permission.ask → permission` (wait=True, tool_summary), `experimental.session.compacting → compact`. Assert `session_id` is prefixed with `"opencode:"`, `pid` is `None`, and unknown tools fall through to `"passthrough"`. Confirm all 6 tests FAIL before implementation.

- [ ] 1.2 [TDD-GREEN] Create `host/clawd_tank_daemon/opencode_protocol.py`: `OPENCODE_SESSION_PREFIX = "opencode:"`, `OPENCODE_DISPLAY_NAME = "OpenCode"`, `OPENCODE_TOOL_ALIASES = {}` (stub with TODO marker), `opencode_hook_payload_to_daemon_message(hook)` implementing all 6 event mappings. Mirror `codex_protocol.py` structure exactly.

- [ ] 1.3 [TDD-GREEN] Add `from .opencode_protocol import opencode_hook_payload_to_daemon_message` to `host/clawd_tank_daemon/__init__.py` (mirrors `codex_protocol` export pattern).

- [ ] 1.4 [TDD-RED] Create `host/tests/test_opencode_integration.py` with a full lifecycle test: feed `session.created` → `tool.execute.before` → `tool.execute.after` → staleness eviction through `daemon._handle_message()` with `enable_opencode=False` then `True` gate. Verify session keyed by `"opencode:..."`, appears in `products[]`, and is evicted. Mark all FAIL before daemon change.

- [ ] 1.5 [TDD-GREEN] In `host/clawd_tank_daemon/daemon.py`: add `("opencode:", "opencode")` to `SESSION_AGENT_PREFIXES` tuple (line ~172). Add `enable_opencode=True` preference (default `True`). In `_handle_message()`: when `enable_opencode` is `False`, silently discard messages whose `session_id` starts with `"opencode:"` (same pattern as future-proof `enable_codex` gate). Wire `opencode_hook_payload_to_daemon_message` into `_AGENT_TRANSLATORS` dict.

## Phase 2: Installer hooks

- [ ] 1.6 [TDD-RED] Create `host/tests/test_opencode_hooks_install.py` mirroring `test_codex_hooks_install.py` patterns: fresh install creates plugin file + backs up `opencode.json` + merges plugin entry; idempotent second call is no-op; missing `opencode.json` returns `OPENCODE_NOT_INSTALLED` error; uninstall restores backup and removes plugin file; uninstall when never installed is no-op. Use `tmp_path` fixture with `monkeypatch`. Mark all FAIL before implementation.

- [ ] 1.7 [TDD-GREEN] In `host/clawd_tank_menubar/hooks.py`: add `OPENCODE_PLUGIN_PATH` (platform-aware path: `~/.config/opencode/plugins/clawd-tank.js` POSIX, `%APPDATA%\\opencode\\plugins\\clawd-tank.js` Windows). Add `OPENCODE_CONFIG_PATH` (platform-aware: `~/.config/opencode/opencode.json` POSIX, `%APPDATA%\\opencode\\opencode.json` Windows). Add `OPENCODE_BACKUP_SUFFIX = ".clawd-tank.bak"`. Implement `install_opencode_hooks()`: backup → atomic read → validate JSON → merge `"file:///..."` into `"plugin"` array → atomic write. Implement `uninstall_opencode_hooks()`: restore backup, delete plugin file. Implement `are_opencode_hooks_installed()`: check plugin file exists AND `opencode.json` has our entry. Implement `resolve_plugin_source()`: return bundled plugin path (mirrors `resolve_mod_source()`). Add `_is_our_opencode_plugin()`, `_our_opencode_plugin_entry()` helpers. **Open question Q1**: plugin shim path injection — use `__filename` self-locate (plugin knows its own path) via `import.meta.url` (Node ESM) or `fileURLToPath(import.meta.url)`; the installed plugin copies itself to a known location so it can self-locate. **Open question Q2**: sibling `package.json` — do NOT require one at the plugin location; OpenCode's plugin loader references the file directly, not the folder.

- [ ] 1.8 [TDD-GREEN] In `host/clawd_tank_menubar/controller.py`: add `install_opencode_hooks()` method mirroring `install_kiro_hooks()` pattern — calls `hooks.install_notify_script()` first, then `hooks.install_opencode_hooks()`, alerts on failure/success. Add `uninstall_opencode_hooks()` method.

## Phase 3: Menu items

- [ ] 1.9 [TDD-GREEN] In `host/clawd_tank_menubar/rumps_view.py`: add `"Install OpenCode Hooks"` menu item calling `controller.install_opencode_hooks()`. Use ` rumps.MenuItem` with standard pattern. **Confirm**: existing Codex/Kiro menu items use ` rumps.MenuItem` (not `rumps.menu_item`).

- [ ] 1.10 [TDD-GREEN] In `host/clawd_tank_menubar/windows_tray.py`: add identical `"Install OpenCode Hooks"` menu item.

- [ ] 1.11 [TDD-GREEN] In `host/clawd_tank_menubar/__main__.py`: add `install-opencode-hooks` and `uninstall-opencode-hooks` CLI commands mirroring `install-codex-hooks` / `uninstall-codex-hooks` pattern.

- [ ] 1.12 Run PR1 focused test suite: `cd host && .venv/Scripts/python.exe -m pytest tests/test_opencode_protocol.py tests/test_opencode_hooks_install.py -v`. Confirm all green. Open PR1 (base=main).

---

# PR 2 — JS plugin + Python bridge + desktop renderer + integration tests

## Phase 4: Plugin source (JS)

- [ ] 2.1 [TDD-RED] Create `host/opencode-plugin/tests/test_opencode_plugin.test.mjs` using Node's built-in `node:test`. Mock `$.spawnSync` (the BunShell API). Verify: `session.created` fires → correct JSON written to payload temp file and `spawnSync` called with correct args; on first `spawnSync` failure, retry fires after ~500ms; on second failure, error is swallowed silently (no unhandled exception). **Open question Q3**: use `Bun.spawnSync(["python3", ..., payloadPath], {timeout: 5000})` when `typeof Bun !== "undefined"`; fall back to `child_process.spawnSync` when running under Node. **Open question Q4**: `@opencode-ai/plugin` peer dep — declare `"@opencode-ai/plugin": "*"` as `peerDependency` in `package.json`; in `clawd-tank-opencode.js`, import types only when `@opencode-ai/plugin` is reachable at runtime (loose event shapes otherwise). Mark all tests FAIL before plugin implementation.

- [ ] 2.2 [TDD-GREEN] Create `host/opencode-plugin/clawd-tank-opencode.js` (plain JavaScript, ESM module). Register all lifecycle hooks (`event`, `tool.execute.before`, `tool.execute.after`, `permission.ask`, `experimental.session.compacting`, `dispose`). Per event: write JSON payload to temp file, spawn Python bridge with `Bun.spawnSync` / `child_process.spawnSync` (5s timeout), swallow errors with one retry + 500ms backoff. **Q1 resolution**: use `import.meta.url` + `fileURLToPath` to self-locate the plugin file; the Python bridge path is derived from the plugin's own directory (`../opencode-bridge.py` relative to plugin location on POSIX, or the installed `~/.clawd-tank/opencode-bridge.py` on both platforms). **Q2 resolution**: no sibling `package.json` required on target machine; OpenCode loads the file directly.

- [ ] 2.3 [TDD-GREEN] Create `host/opencode-plugin/package.json` with `private: true`, `"type": "module"`, `"@opencode-ai/plugin": "*"` as `peerDependency`. Scripts: `test` runs `node --test`. **Q4 confirmation**: `@opencode-ai/plugin` is a peer dependency only — the plugin uses runtime import guards rather than hard TypeScript compile-time dependency.

- [ ] 2.4 Run JS tests: `node --test host/opencode-plugin/tests/test_opencode_plugin.test.mjs`. Confirm all green.

## Phase 5: Python bridge

- [ ] 2.5 [TDD-GREEN] In `host/clawd_tank_menubar/hooks.py`: add `OPENCODE_BRIDGE_SCRIPT` constant (mirrors `NOTIFY_SCRIPT` pattern, stdlib-only). Sends to daemon socket using the same POSIX/Windows socket logic as `NOTIFY_SCRIPT`. Translates OpenCode event to daemon message inline (same as `opencode_hook_payload_to_daemon_message` logic). **Note**: this is a copy of the translation logic in the Python bridge because the bridge cannot import `opencode_protocol.py` (it must be stdlib-only). Keep in sync manually. Adds `opencode_bridge.py` (POSIX) / `opencode-bridge.py` (Windows) to `CLAWD_DIR`.

- [ ] 2.6 [TDD-GREEN] In `host/clawd_tank_menubar/hooks.py`: `install_opencode_hooks()` also writes the bridge to `~/.clawd-tank/opencode-bridge.py` (POSIX: extensionless; Windows: `.py`). Use same atomic-write helper as `install_notify_script()`.

- [ ] 2.7 [TDD-RED] In `host/tests/test_opencode_bridge.py` (new file): mock socket write, assert payload shape for each event type. Assert `session_id` prefixed with `"opencode:"`, `pid=None`, `event` field correct for each mapping. Mark FAIL before bridge implementation.

## Phase 6: Desktop pet renderer

- [ ] 2.8 [TDD-GREEN] In `desktop/main.js`: add `"opencode"` to `AGENT_ORDER` array (line 37: `["claude", "codex", "kiro", "opencode"]`).

- [ ] 2.9 [TDD-GREEN] In `desktop/renderer/renderer.js`: add `AGENT_LABELS.opencode = "OpenCode"`.

- [ ] 2.10 [VERIFY] `desktop/renderer/anim-map.js` — no changes needed (product-agnostic; confirmed in design). Document verification: grep for any `agent === "codex"`-style explicit checks; confirm none match `"opencode"` in a way that would break.

## Phase 7: Integration tests

- [ ] 2.11 [TDD-RED] In `host/tests/test_opencode_integration.py`: add full lifecycle test (registered → working → idle → evicted). Feed payloads through `daemon._handle_message()` → assert session in `daemon._sessions`, assert correct `products[]` entry with `agent: "opencode"`. Confirm stale eviction after 10min timeout. Mark FAIL before daemon changes in PR1 + this test.

- [ ] 2.12 Run PR2 focused test suite: `cd host && .venv/Scripts/python.exe -m pytest tests/test_opencode_protocol.py tests/test_opencode_integration.py tests/test_opencode_hooks_install.py tests/test_opencode_bridge.py -v`. Confirm all green. Open PR2 (base=PR1 branch; retarget to main after PR1 merges).

---

# PR 3 — Bundling + verify

## Phase 8: Bundling

- [ ] 3.1 [TDD-GREEN] In `host/setup.py`: add `("opencode-plugin", ["opencode-plugin/clawd-tank-opencode.js"])` to `DATA_FILES`. **Confirm**: the tuple is `(destination folder name, [source paths relative to `host/`])`; the destination name is what py2app creates under `Resources/`, so it must match the folder `hooks.install_opencode_hooks()` copies from at runtime.

- [ ] 3.2 [TDD-GREEN] In `host/windows/margarita_tank.spec`: add `(os.path.join(REPO_ROOT, "host", "opencode-plugin", "clawd-tank-opencode.js"), "opencode-plugin")` to `datas`. Follow the existing entries in `datas=[...]`: first element is the absolute source path (build from `REPO_ROOT`), second is the destination folder inside the bundle.

- [ ] 3.3 [TDD-RED] Create `host/tests/test_opencode_plugin_packaging.py`: assert `setup.py` `DATA_FILES` contains `"opencode-plugin"` entry; assert `margarita_tank.spec` `datas` contains `"opencode-plugin"` entry; assert `resolve_plugin_source()` returns a valid filesystem path for dev, py2app, and PyInstaller cases. Use `monkeypatch` to patch `sys.frozen` and `sys.executable`. Mark FAIL before bundling changes.

- [ ] 3.4 [VERIFY] Check `.github/workflows/release.yml` — if it asserts any plugin bundles, mirror the assertion for `opencode-plugin`; otherwise note "no change needed". Confirm `release.yml` bundles `clawd-tank-sim.exe` from the simulator build.

## Phase 9: Integration verification

- [ ] 3.5 Run full host pytest suite: `cd host && .venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_ble.py --ignore=tests/test_ble_client.py -x`. Capture green output. Note: `test_ble.py` and `test_ble_client.py` are excluded (BLE hardware-specific, may hang on Windows without hardware; pre-existing behavior).

- [ ] 3.6 [MANUAL] Install hooks on dev machine: run `python -m clawd_tank_menubar install-opencode-hooks`; launch OpenCode desktop app; observe crab animation. Document `session.created` / `tool.execute.*` lifecycle events received by daemon. Capture screenshot if crab appears.

- [ ] 3.7 [VERIFY] Menu item exercise: click "Install OpenCode Hooks" in menu bar app → verify plugin installed to `~/.config/opencode/plugins/clawd-tank.js` and `opencode.json` has plugin entry → click again → verify idempotent (no duplicate entry) → uninstall via `python -m clawd_tank_menubar uninstall-opencode-hooks` → verify backup restored and plugin file removed.

## Phase 10: Cleanup

- [ ] 3.8 Update `TODO.md` with new feature block: OpenCode integration (plugin + bridge + daemon translator + menu item + desktop pet renderer + bundling).

---

## Open Question Resolutions

| # | Question | Resolution in Tasks |
|---|----------|---------------------|
| Q1 | Plugin shim path injection strategy | Task 2.2: use `import.meta.url` + `fileURLToPath` (Node ESM) to self-locate plugin file. Bridge path derived from plugin's own directory on dev; on installed builds, `resolve_plugin_source()` returns the bundled path and the plugin file is copied to `~/.config/opencode/plugins/`. |
| Q2 | Sibling package.json needed on target? | Task 2.3: `private: true`, no `package.json` at plugin location on target machine. OpenCode's plugin loader uses `file:///` reference to the `.js` file directly. |
| Q3 | BunShell sync spawn API | Task 2.2: `Bun.spawnSync(["python3", ..., payloadPath], {timeout: 5000})` when `typeof Bun !== "undefined"`; fallback to `child_process.spawnSync` when running under Node. |
| Q4 | `@opencode-ai/plugin` peer-dep | Task 2.3: declared as `"@opencode-ai/plugin": "*"` in `peerDependencies`. Task 2.2: runtime import guard — use loose event shapes when the package is not reachable; only import types when `@opencode-ai/plugin` is installed in the user's env. |

## Out-of-Scope Reminders (from Design)

- No firmware/simulator changes (firmware/ and simulator/ are untouched)
- No npm publish of the plugin (`private: true`, no distribution via npm)
- No OpenCode-specific crab art (falls through to default clawd)
- No subagent tracking (OpenCode emits no `SubagentStart/Stop`)
- No PID tracking (`pid = None` always)
- Generic notification card text (same as Codex/Kiro)
- No changes to `pid_resolver.py`, `ble_service.c`, `scene.c`, or any simulator-specific code
