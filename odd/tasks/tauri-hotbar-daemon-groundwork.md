# Tauri hotbar: shell-agnostic daemon groundwork (Change 1)

Host-only, 4 stacked PRs on top of `feat/monster-default-pet` (design line numbers match that HEAD, not `main`).
Work happens in worktree `O:\Proyectos\Clawdy-hotbar` (branch `feat/hotbar-daemon`) because another session edits the main tree.
Source of truth: `openspec/changes/tauri-shell-hotbar-migration/{proposal,design,tasks}.md` + `specs/*/spec.md`. Engram mirror unavailable (binary predates v2.0.0-rc.11); this file is the record.

## Specs

- S1 `openspec/changes/tauri-shell-hotbar-migration/specs/claude-usage-reader/spec.md` (read in full; its scenarios are the examples)
- S2 `.../specs/project-usage-transport/spec.md`
- S3 `.../specs/hook-command-resolution/spec.md`
- S4 `.../specs/headless-daemon/spec.md`
- S6 Windows build name: main exe `Clawdy.exe` in folder `dist/Clawdy`; installer AppName/AppExeName/BuildDir/icon say Clawdy; helper exes, AppId, publisher, release asset name, data paths keep their names (L4).
- S5 Design decisions: `.../design.md`; task breakdown and RED/GREEN order: `.../tasks.md`

## Tasks

- T1 S1,S5 · PR1 usage reader (tasks.md 1.1-1.10) · inline · branch `feat/hotbar-usage-reader` · commit: 96a9c79
- T2 S2,S5 · PR2 `set_project_usage` transport (2.1-2.6) · inline · commit: 8f7a927
- T3 S3,S5 · PR3 hook executable resolution (3.1-3.7) · inline · commit: 11eb877
- T4 S4,S5 · PR4 headless parity (4.1-4.6) · inline · commit: 480f5ec

## Log

- L1 (user) "con eso definido podriamos continuar con esto O:\Proyectos\Clawdy\openspec\changes\tauri-shell-hotbar-migration"
- L2 (evidence) Base is current HEAD, not `main`: `hooks.py` is 1534 lines on main vs 2575 on HEAD and the design cites HEAD lines (`hooks.py:1107-1165`, `daemon.py:1674`). Pre-existing uncommitted `CLAUDE.md` style block is the user's; stage only own hunks.
- L3 (evidence) PRs opened on sam-wilkie/margarita-tank, stacked: #7 pr1 -> opencode-product-pr1, #8 pr2 -> pr1, #9 pr3 -> pr2, #10 pr4 -> pr3. Verify fixes c169f2d ride in #10. Base `opencode-product-pr1` (afcf40c) has no PR of its own yet.
- L4 (user, requirement change) "ya no deberia llamarse margaritatank, sino clawdy.exe" → answered "Exe y nombre visible". Conflicts with the original preservation contract ("branding stays unchanged"); user confirmed the change. Scope decided here: main exe, install folder, installer AppName/AppExeName/BuildDir/icon, tray-generated comment. Kept: AppId, publisher, release asset name `Margarita-Tank-Setup.exe` (README/release links), helper exes `margarita-notify.exe` and `margarita-statusline.exe` (hooks depend on them), data paths, BLE device name "Margarita".
- L5 (evidence) gitnexus_impact not run: `npx gitnexus` is not installed and the MCP tool is not available in this session. Reported at close.

## Tasks (reopened)

- T5 S6 · rename the Windows build to Clawdy.exe (tests in host/tests/test_release_names.py) · inline · commit: b26a8d2
