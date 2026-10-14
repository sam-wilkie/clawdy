# Monster default pet

Animated desktop-pet art set for the brand monster (round red/white, eight ring eyes), parallel to the Claude crab.
Branch: `feat/monster-default-pet`. Engram mirror unavailable (Engram binary too old); this file is the record.

## Specs

- S1 "es un pet paralelo al de claude que ya existe para que sea el modelo por defecto": the monster is a separate art set next to the Claude crab (and the Codex cloud), and it is the pet shown for any agent that has no art set of its own.
- S2 "crear las animaciones por default ... basadas en las animaciones existentes": every monster state reuses the beats, fps and loop of the existing v2 state of the same name, except where the grid v2 key pose (S3) replaces the prop: `building` (code blocks, 3 s at 8 fps) and `cool` (thumbs-up, same timing).
- S3 (superseded by S5 for the look) Design source: `assets/pet-samples/ai/monster-brand-cute-v1.png` (character) and `assets/pet-samples/ai/monster-brand-activities-grid-v2.png` (per-activity key poses): circular body, white left side with a red right crescent, the ring-eye cluster of the cute-v1 image (nine rings: three red, six white), small smile with two baby fangs, blush, floating white left and red right mittens.
- S4 Scope "Los 31 estados": one SVG per state the Codex cloud set ships. That set has 29 files (idle, waiting_reply and 27 rendered states, alert included); "31" was a miscount in the option label.

- S5 Redesign approved by the user ("me gusta la opcion 2", mockup `monster-redesign-ideas-v5.png`): three big ring eyes in one touching arched row just above the mouth ("los ojos deben ir juntos todos no separados para respectar un poco la marca, a menos que este con los ojos cerrados que alli si se verian feos o raros"), mittens kept ("no tiene las manitas que ayudan en las animaciones"), tonal outlines, softer cherry, no stray silhouette pixels.
- S6 "me gustaria que este tuviera las animacion de error, low battery, happy, sweeping, beacon, debugger, y waiting_reply, sleeping, alert, disconnected como el cangrejo": those ten states follow the crab's beats, fps and loop.

## Tasks

- T1 S2-S4 · generator `tools/monster_pixel.py` writing `desktop/renderer/assets/monster/monster-<state>-v2.svg` + gallery · inline · commit: c8f4918
- T2 S1 · renderer selects the monster set for agents without their own art; test · inline · commit: a05b91d
- T3 S1-S4 · render every state to PNG and inspect; update TODO.md and docs · inline · commit: see git log (docs commit)

- T4 S5-S6 · port the option-2 design into the generator and give the ten states the crab's beats · inline · commit: a130af2

- T5 S6 + L23 · bigger mittens, crab-skinned states, welding building · inline · commit: 6932354

- T6 L25 · centred disconnected marks (crab too), bare X error eyes, crab sleeping, calm sweeping eyes, big wizard hat · inline · commit: 73a6325

- T7 L27 · three-lens shades on the crab cool, crab-style X, Codex cool on the crab animation (local) · inline · commit: ef48fbc

- T8 L29 · pet art bible + contact-sheet tool · inline · commit: 9193b7a
- T9 L29 L31 · new-pet skill + pet_check validator · inline · commit: 19594d1

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
- L13 (user) "agrega el claude a la pantalla y no me gusta mucho diseño se ve muy saturado, porq crees q sea?"
- L14 (evidence) compare-v2.html now shows Claude v2 | Codex v2 | Monster v2 per state. Redesign for the saturation feedback awaits the user's choice.
- L15 (user) "porq el de claude se siente mas pulido y me gustaria que este tuviera las animacion de error, low battery, happy, sweeping, beacon, debugger, y waiting_reply, sleeping, alert, disconnected como el cangrejo, pero antes de animarlo, quiero que me muestres una idea de como mejorarlo nates de volver a gastan en mas token diseñando nuevo"
- L16 (evidence) Static mockup `assets/pet-samples/ai/monster-redesign-ideas-v1.png` (local, gitignored): crab | current | A 9 clean eyes | B 5 eyes | C 3 eyes, tonal outlines and softer cherry. Current body also has 1 px nubs at top/bottom/sides (mask lacks the cloud's nub cleanup). Awaiting the user's pick before animating.
- L17 (user) "me gusta la C pero no tiene las manitas que ayudan en las animaciones, de pronto los ojos mas grandes"
- L18 (evidence) Mockup `assets/pet-samples/ai/monster-redesign-ideas-v2.png` (local): C2 with three 7x8 eyes (2x2 catch-light + small lower one), white left / red right mittens, poses rest, happy (hands up, ^ ^ eyes, open grin) and thinking (mitten at the chin). Awaiting confirmation before animating.
- L19 (user) "bajale mas los ojos que queden mas cerca de la boca y muestrame como quedara en el tamaño del claude"
- L20 (evidence) Mockup `assets/pet-samples/ai/monster-redesign-ideas-v3.png` (local): C3 = eyes lowered 4 art px next to the mouth, right eye ring in dark red on the crescent, darker mitten outlines; placed with the pet's own mapping (viewBox -15 -25 45 45, art px = 0.5 unit) beside the crab at 180 px (real pet size) and 360 px. Same width as the crab, but taller because it is round.
- L21 (user) "me gusta la opcion 2"
- L22 (evidence) T4: generator rewritten. Own crab-beat renderers for error (2.4 s, 10 fps), low_battery (8 s, 6 fps), happy (2 s, 10 fps), beacon (2 s, 8 fps), debugger (12 s, 8 fps), waiting_reply (2 s, 8 fps), alert (4 s, 10 fps, the crab's notification beats), disconnected (3.2 s, 10 fps). sleeping and sweeping keep the engine's poses, which already copy the crab's beats (6 s/6 fps and 1.5 s/8 fps). Regeneration deterministic (two runs, same checksum), codex/*.svg unchanged, desktop npm test 45/45. Rendered and inspected with Playwright. Size kept as in the mockup (the user did not ask to shrink it).
- L23 (user) "podrias hacer las manitas mas grandecitas para que tengan un poco mas de detalle, porq parecen un pixel ah sin forma, beacon no se parece a la de claude, debbuger tiene que tener la lupa mas grande para que se vea como el claude, me gusta mas la nube de pendamiento de claude en thinking, para building me gustaria una animacion mas relacionada a construir que no sea la misma de claude yu codex porq parece que estuviera armando legos, en wizard y hat mizhap el gorro tan pequeño es absurdo, codex corre con el mismo error en esa animaciones, disconected cambiaste por completo lo que te pedi, y low battery mas de lo mismo, te pedi que fuera como claude igual que sweeping"
- L24 (evidence) T5: mittens 8x7 with a thumb lobe and crease. beacon, debugger, thinking, disconnected, low_battery, sweeping, wizard and hat_mishap are now the crab's own SVG files re-skinned (crab_skin: legs emptied, torso -> monster body + mouth, pincers -> mittens at the pincer centre, eye groups -> monster eyes, head props moved up 10 px, hats 6 px), so scene, props and CSS timing are the crab's. building is a new welding animation (torch on a steel I-beam, sparks, cooling seam, smoke). Deterministic regeneration, codex/*.svg unchanged, desktop npm test 45/45; frames inspected with Playwright. Not done: the Codex cloud's small wizard hat (user reported it); awaiting a go-ahead because it changes the local-only cloud set.
- L25 (user) "disconnected tiene como un error con esos dos signos de puntuacion o es pregunta o interrogante y sin ambas deberian estar en el medio para que no se vea raro, pasa en el de claude como en el que estamos haciendo, en error podras colocar directamente las X sin el circulo, en sleeping usa la misma animacion de claude incluyendo las letras ZZZZ, y sweeping hay un error que mueve los ojos a los lados como si se los quitara, en wizar haz el gorro mas grande y que quede justo a la altura de los ojos, todo lo demas quedo perfect"
- L26 (evidence) T6: Claude `clawd-disconnected-v2.svg` "?" moved from x 1 to x 13 so it is centred over the head like the "!" (x 14); the monster inherits it. error: bare ink X eyes, no rings. sleeping: the crab's own file re-skinned (sploot breaths, blush, the three floating Zs, moved up 12 px). sweeping: the crab's 3..9 px eye slide mapped to 0..2 px with the same lean on the body. wizard: the crab's hat redrawn 32 px wide (nearest-neighbour on whole pixels), brim bottom at y 11 on top of the eyes. Deterministic, codex unchanged, desktop npm test 45/45, frames inspected.
- L27 (user) "para la de cool podrias crear un lente para tres ojos y colocarlo con la animacion de claude, asi mismo arregla la animacion de Codex para que tenga la misma animacion que esa que tiene no me gusta nada. y la X de error que se vizualice mas estilo Claude"
- L28 (evidence) T7: new `tools/crab_skin.py` (def_groups, bbox, raster, skin) shared by the monster and the local Codex generator; monster refactor kept every other state byte-identical. Monster cool = the crab's clawd-cool-v2.svg with three-lens shades (bar + one lens per eye, crab glint). Monster error X = the crab's bold 6x6 X with its flat mouth. Codex cloud cool (local-only, gitignored) = the crab's cool re-skinned with the cloud body, >_ face, puff hands and its pixel shades; only cloud-cool-v2.svg changed among the codex files. desktop npm test 45/45.
- L29 (user) "perfecto, con esto definido podrias crear un art bible que funcione como el para acelerar estos procesos de como deben crearse los futuras mascotas,tamaño, animacones, reglas que debe respetar, y basado en esto crear un hook que ayude a minimizar los costes y gasto en token"
- L30 (evidence) T8: `docs/pet-art-bible.md` (canvas, pixel rules, parts, 29 states and routes, review lessons, the three ways to make a state, cheap workflow, sets) and `tools/pet_sheet.py` (one contact-sheet PNG per batch). Hook: kind awaiting the user's choice.
- L31 (user) hook choice: "el hook es para usarlo cada vez q se vayan a crear nuevas mascotas y el proceso sea mas barato porq ya sabe que hacer"
- L32 (evidence) T9: skill `new-pet` in `.agents/skills/new-pet/SKILL.md` (pi) with a pointer in `.claude/skills/new-pet/SKILL.md` (Claude Code): recipe, which generator parts to change, cheap review loop. `tools/pet_check.py` validates a set without rendering (29 states from renderer.js STATES + alert, viewBox per state, whole-pixel paths); RED (4 failures, no script) then GREEN `python -m unittest tools.tests.test_pet_check` 4/4; monster and cloud sets pass.
