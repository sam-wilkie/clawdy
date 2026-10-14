# Monster default pet

Animated desktop-pet art set for the brand monster (round red/white, eight ring eyes), parallel to the Claude crab.
Branch: `feat/monster-default-pet`. Engram mirror unavailable (Engram binary too old); this file is the record.

## Specs

- S1 "es un pet paralelo al de claude que ya existe para que sea el modelo por defecto": the monster is a separate art set next to the Claude crab (and the Codex cloud), and it is the pet shown for any agent that has no art set of its own.
- S2 "crear las animaciones por default ... basadas en las animaciones existentes": every monster state reuses the beats, fps and loop of the existing v2 state of the same name, except where the grid v2 key pose (S3) replaces the prop: `building` (code blocks, 3 s at 8 fps) and `cool` (thumbs-up, same timing).
- S3 Design source: `assets/pet-samples/ai/monster-brand-cute-v1.png` (character) and `assets/pet-samples/ai/monster-brand-activities-grid-v2.png` (per-activity key poses): circular body, white left side with a red right crescent, the ring-eye cluster of the cute-v1 image (nine rings: three red, six white), small smile with two baby fangs, blush, floating white left and red right mittens.
- S4 Scope "Los 31 estados": one SVG per state the Codex cloud set ships. That set has 29 files (idle, waiting_reply and 27 rendered states, alert included); "31" was a miscount in the option label.

## Tasks

- T1 S2-S4 · generator `tools/monster_pixel.py` writing `desktop/renderer/assets/monster/monster-<state>-v2.svg` + gallery · inline · commit: c8f4918
- T2 S1 · renderer selects the monster set for agents without their own art; test · inline · commit: a05b91d
- T3 S1-S4 · render every state to PNG and inspect; update TODO.md and docs · inline · commit: see git log (docs commit)

## Log

- L1 (user) "necesito que usando el modelo Opus 5.5 me ayudes a crear las animaciones por default O:\Proyectos\Clawdy\assets\pet-samples\ai\monster-brand-cute-v1.png basadas en las animaciones existentes  y O:\Proyectos\Clawdy\assets\pet-samples\ai\monster-brand-activities-grid-v2.png puedes mirar las memorias de codex respecto a esto"
- L2 (user) scope choice: "Los 31 estados (Recomendado)".
- L3 (user) "es un pet paralelo al de claude que ya existe para que sea el modelo por defecto"
- L4 (user) model switched to Opus 5.5 ("listo ya lo hice"); PI_MODEL=claude-opus-5-5 confirmed.
- L5 (evidence) Codex memory store `~/.codex/memories` is empty; context comes from Codex session 2026-10-13 (rollout-2026-10-13T10-49-09): v1 cute design chosen, 30-pose grid v1 then v2 (CONSTRUYENDO = code blocks, COOL = thumbs-up without glasses).
- L6 (decision) Mapping for S1: claude keeps the crab, codex keeps the cloud, every other agent (kiro, opencode, antigravity, unknown) gets the monster. The generator skins the Codex cloud engine (`tools/codex_cloud_pixel.py`: same poses, props and timing) with the monster body, faces and mittens, so the cloud output is untouched.
- L7 (evidence) The cute-v1 image has nine ring eyes (3 red, 6 white), although the Codex prompt said eight; the art follows the image. The Codex cloud set has 29 states, not 31.
- L8 (evidence) T1: `python tools/monster_pixel.py` writes 29 SVGs + compare-v2.html; codex/*.svg checksums unchanged (478f807c... before and after). Building (code blocks) and cool (thumbs-up, no glasses) follow grid v2 instead of the cloud's hammer and sunglasses. Every state rendered with Playwright and inspected.
- L9 (evidence) T2: RED observed (kiro got the crab: `art: undefined`, `ART_STATES.idle` null), then GREEN; `npm test` in desktop: 45 pass, 0 fail. waiting_reply calm override stays Codex-only, so the monster shows its waiting_reply bubble like the crab.
- L10 (evidence) T3: README "Estados de la mascota" and TODO.md updated. Not verified in a real Electron window.
- L11 (evidence) Independent verify (gentle-ai-verify, native assess unassessable -> treated as high): S1, S3, S4 met; S2 met except `building` timing, now documented in S2. npm test 45/45, regeneration byte-identical, codex assets unchanged, no crab/cloud regression found.
- L12 (open) `tools/codex_cloud_pixel.py` and `desktop/renderer/assets/codex/` are gitignored (licensing, NOTICE.md), so `tools/monster_pixel.py` cannot run on a fresh clone; the committed monster SVGs are self-contained. Generator now exits with a clear message. Decision pending from the user: keep as is, or move the generic engine into a tracked module.
