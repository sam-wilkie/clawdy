# Tauri 2 spike (Change 0, throwaway)

Go/no-go for the Tauri shell migration. Branch `spike/tauri-hotbar` (worktree `O:\Proyectos\Clawdy-hotbar`), never merged; code lives under `spike/tauri/`.
Source: `openspec/changes/tauri-shell-hotbar-migration/exploration.md` ("Change 0"). Engram mirror unavailable (binary predates v2.0.0-rc.11); this file is the record.

## Specs

- S1 Scope of go/no-go: "Windows y macOS". Windows is verified here. macOS cannot be run on this machine: its criteria are written, but only the user can mark them pass/fail on a Mac.
- S2 Window: transparent, always-on-top, frameless Tauri 2 window showing a pet sprite.
- S3 Click-through: selective, driven by Rust cursor polling (Tauri has no `forward`, tauri#13070). Clicks pass through transparent pixels and are captured on the pet.
- S4 Permission round trip: an Allow/Deny card sends a real `permission_decision {id, nonce}` through the existing daemon (TCP 127.0.0.1:19872) and the daemon resolves the pending request.
- S5 Thresholds (proposed by the agent, user chose "Propuestos por mí"):
  - T-click: click-through is correct on every sampled point (pet pixels capture, transparent pixels pass through) and switches in under 50 ms.
  - T-cpu: idle CPU under 1 % averaged over 60 s.
  - T-ram: working set under 150 MB at idle.
  - T-perm: Allow and Deny each resolve the real pending permission once; a wrong nonce is rejected and changes nothing.
  - T-mac (user-run): same T-click and T-perm on macOS, plus visibility over a fullscreen app (tauri#11488 / #14102 risks). Result: unverified until the user runs it.
- S6 Verdict format: a table of S5 rows with measured value, pass/fail, and a final GO / NO-GO. B (Electron + electron-builder) is the fallback on NO-GO.

## Tasks

- T1 S5 · install Rust (rustup, stable) and MSVC Build Tools; verify `cargo --version` and a hello-world build · inline · commit: this commit
- T2 S2,S3 · scaffold `spike/tauri/`, transparent always-on-top window with a sprite, Rust cursor-polling click-through · inline · commit: see git log (spike commits)
- T3 S4 · Allow/Deny card round-tripping a real nonce through the daemon · inline · commit: see git log (spike commits)
- T4 S5,S6 · measure T-click/T-cpu/T-ram/T-perm on Windows, write the verdict, hand T-mac to the user · inline · commit: see git log (spike commits)

## Log

- L1 (user) "con eso definido podriamos continuar con esto O:\Proyectos\Clawdy\openspec\changes\tauri-shell-hotbar-migration" then "ok" to start the spike.
- L2 (user) go/no-go scope: "Windows y macOS"; thresholds: "Propuestos por mí (recomendado)"; Rust install: "Sí, instalalos".
- L3 (evidence) This machine has node v24.15.0 and npm 11.12.1 but no cargo, rustc or rustup; only the `Installer` and `Shared` folders under Visual Studio, so no confirmed MSVC.
- L4 (decision) C: has ~7.8 GB free, so everything lives on O:. Rust via rustup (`RUSTUP_HOME=O:\devustup`, `CARGO_HOME=O:\dev\cargo`, no PATH change); MSVC 14.44 + Windows SDK 26100 via the portable-msvc.py gist (reviewed; license accepted by the user) into `O:\dev\msvc`; Visual Studio untouched. Activate with `. /o/dev/env.sh`. Verified: `cargo run` hello-world prints "Hello, world!" (cargo 1.99.0).

## Verdict (Windows, release build, 2026-10-13)

| Criterion | Measured | Result |
|---|---|---|
| T-click correctness | pet got 5/5 clicks on its pixels; 0/3 on a transparent corner; a real window underneath got 3/3 of the transparent clicks and 0/3 of the pet clicks | PASS |
| T-click latency (<50 ms) | enter-pet median 5.8 ms, p95 7.8; leave-pet median 7.0 ms, p95 8.6 (flag flip observed from outside, n=40 each) | PASS |
| T-cpu (<1 %, 60 s idle) | 3.81 % of one core = 0.32 % of 12 cores; an 8 ms cursor-polling thread is the likely cause, not tuned | AMBIGUOUS: fails if "one core", passes if "all cores" |
| T-ram (<150 MB) | 340 MB working set, spike + its WebView2 processes | FAIL as written |
| T-perm | Allow -> hook `allow`, daemon `closed: allow`; Deny -> `deny`; wrong nonce -> `Ignored a permission decision`, request `closed: none`. Isolated daemon (temp HOME, port 19999), real `clawd-tank-notify` | PASS |
| T-mac | not run | UNVERIFIED (user-run) |

Not measured: Electron baseline CPU/RAM for the same scene, so "lighter than Electron" is unproven; polling interval tuning; one pet window only (the real shell has several); Windows only.
Gotcha found: without `capabilities/default.json` (`core:default`) the page cannot call any command, so buttons silently did nothing.

**Verdict: NOT a clean GO.** The hard technical risks (selective click-through via polling, real nonce round trip) are proven on Windows. The footprint criteria are not met as written (RAM) or are ambiguous (CPU), and macOS is untested. Decision needed from the user, see L5.

## Log (cont.)

- L5 (open) Needs the user: (a) accept 340 MB or compare against Electron's measured footprint before judging; (b) define T-cpu per core or per machine; (c) run T-mac on a Mac.

