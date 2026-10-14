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

- T1 S5 · install Rust (rustup, stable) and MSVC Build Tools; verify `cargo --version` and a hello-world build · inline · commit: pending
- T2 S2,S3 · scaffold `spike/tauri/`, transparent always-on-top window with a sprite, Rust cursor-polling click-through · inline · commit: pending
- T3 S4 · Allow/Deny card round-tripping a real nonce through the daemon · inline · commit: pending
- T4 S5,S6 · measure T-click/T-cpu/T-ram/T-perm on Windows, write the verdict, hand T-mac to the user · inline · commit: pending

## Log

- L1 (user) "con eso definido podriamos continuar con esto O:\Proyectos\Clawdy\openspec\changes\tauri-shell-hotbar-migration" then "ok" to start the spike.
- L2 (user) go/no-go scope: "Windows y macOS"; thresholds: "Propuestos por mí (recomendado)"; Rust install: "Sí, instalalos".
- L3 (evidence) This machine has node v24.15.0 and npm 11.12.1 but no cargo, rustc or rustup; only the `Installer` and `Shared` folders under Visual Studio, so no confirmed MSVC.
