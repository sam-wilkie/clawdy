# Hook Command Resolution Specification

## Purpose

Notify and statusLine commands are built from `sys.executable` at import (`hooks.py:1107-1167`). Resolution SHALL take platform, frozen state, executable/notify location and script path as explicit inputs while producing today's commands for current layouts.

## Requirements

### Requirement: Golden equality for current layouts

For every layout below, the new resolution MUST return exactly the string `build_hook_command` / `build_statusline_command` return today.

| Layout | Hook command | StatusLine command |
|---|---|---|
| macOS/Linux (frozen or dev) | script path | `/bin/sh <shlex-quoted script>` |
| Windows dev | `"<python.exe>" "<script>"` | same shape |
| Windows dev under `pythonw.exe` | `pythonw.exe` replaced by `python.exe` | `"<exe>" "<script>"` |
| Windows frozen | `"<dir>\margarita-notify.exe"` | `"<dir>\margarita-statusline.exe"` |

#### Scenario: Golden strings
- GIVEN each layout with paths containing spaces
- WHEN commands are resolved
- THEN each equals the pre-change string byte for byte

### Requirement: Explicit notify location

The executable directory MAY be supplied explicitly via `CLAWD_TANK_HOOK_EXE_DIR` (for example a sidecar daemon in another folder). When valid (absolute, contains both `margarita-notify.exe` and `margarita-statusline.exe`, no `"` in the path), it MUST determine both the notify and statusLine commands instead of `sys.executable`; when absent or invalid, today's behavior applies.

#### Scenario: Daemon moved
- GIVEN Windows frozen layout and a valid explicit directory
- WHEN resolved
- THEN the hook command names `margarita-notify.exe` and the statusLine command names `margarita-statusline.exe` in that directory

### Requirement: Re-point dead hooks

On startup, a managed hook whose command names a missing executable or script MUST be rewritten to the current command. A hook whose target exists and equals the current command MUST be left unchanged. Hooks not owned by us MUST never be modified (ownership rule `hooks.py:1757`).

#### Scenario: Missing notify exe
- GIVEN settings.json points at a deleted `margarita-notify.exe`
- WHEN startup install runs
- THEN our groups use the current command; a user's own hooks are byte-identical

#### Scenario: Up to date
- GIVEN hooks already current
- WHEN startup install runs
- THEN settings.json is not rewritten

### Requirement: Non-regression

The managed event set, ownership/prune rules, `--uninstall-hooks`, and `are_hooks_installed()` semantics MUST be unchanged. The notify script MUST remain stdlib-only.

#### Scenario: Uninstall
- GIVEN hooks installed by new resolution
- WHEN uninstall runs
- THEN only our groups and statusLine bridge are removed
