# Tauri hotbar: shell-agnostic daemon groundwork (Change 1)

Host-only, 4 stacked PRs on top of `feat/monster-default-pet` (design line numbers match that HEAD, not `main`).
Work happens in worktree `O:\Proyectos\Clawdy-hotbar` (branch `feat/hotbar-daemon`) because another session edits the main tree.
Source of truth: `openspec/changes/tauri-shell-hotbar-migration/{proposal,design,tasks}.md` + `specs/*/spec.md`. Engram mirror unavailable (binary predates v2.0.0-rc.11); this file is the record.

## Specs

- S1 `openspec/changes/tauri-shell-hotbar-migration/specs/claude-usage-reader/spec.md` (read in full; its scenarios are the examples)
- S2 `.../specs/project-usage-transport/spec.md`
- S3 `.../specs/hook-command-resolution/spec.md`
- S4 `.../specs/headless-daemon/spec.md`
- S5 Design decisions: `.../design.md`; task breakdown and RED/GREEN order: `.../tasks.md`

## Tasks

- T1 S1,S5 · PR1 usage reader (tasks.md 1.1-1.10) · inline · branch `feat/hotbar-usage-reader` · commit: 96a9c79
- T2 S2,S5 · PR2 `set_project_usage` transport (2.1-2.6) · inline · commit: 8f7a927
- T3 S3,S5 · PR3 hook executable resolution (3.1-3.7) · inline · commit: 4eda6f4
- T4 S4,S5 · PR4 headless parity (4.1-4.6) · inline · commit: pending

## Log

- L1 (user) "con eso definido podriamos continuar con esto O:\Proyectos\Clawdy\openspec\changes\tauri-shell-hotbar-migration"
- L2 (evidence) Base is current HEAD, not `main`: `hooks.py` is 1534 lines on main vs 2575 on HEAD and the design cites HEAD lines (`hooks.py:1107-1165`, `daemon.py:1674`). Pre-existing uncommitted `CLAUDE.md` style block is the user's; stage only own hunks.
