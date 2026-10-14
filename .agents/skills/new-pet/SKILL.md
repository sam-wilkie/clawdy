---
name: new-pet
description: Create or change a desktop pet art set (Electron pet, desktop/renderer/assets). Use when the user asks for a new pet or mascot, a new character for an agent, or to redraw, fix or re-animate pet states (idle, thinking, cool, wizard, error, ...). Spanish triggers include "crear mascota", "nueva mascota", "mascota por defecto" and "animaciones de la mascota". It gives the fixed recipe and the cheap review loop, so nothing has to be rediscovered.
---

# New desktop pet

The rules live in `docs/pet-art-bible.md`; this skill is the short version. Do not re-explore the generators: everything needed is listed below.

## Recipe

1. **Mockup before code.** Make one static PNG: the crab beside the candidate at 180 px and at 2×, plus 2–3 expressions (rest, happy, closed eyes). Ask for approval. Do not animate before the design is approved.
2. **Generator.** Copy `tools/monster_pixel.py` to `tools/<set>_pixel.py` and change only these parts:
   - the palette block (tonal outlines);
   - `monster_mask` / `monster_shade` (body);
   - `EYES`, `RING`, `SPREAD` and the glyphs (face);
   - `MITTEN` (hands);
   - `OUT` and the `monster-` prefix.

   Keep `crab_skin()`, the `CRAB_EYES` mapping, `HEAD_UP`/`HAT_UP` and the state table (`OWN`, `STATE_RENDERERS`). It needs the local engine `tools/codex_cloud_pixel.py`.
3. **States.** For a state that should be "like Claude", re-skin the crab's file with `crab_skin(state, "clawd-<file>-v2.svg", shifts)`.
   - Move head props up by the head-top difference (the crab's top is y = 12).
   - Hats are as wide as the head, with the brim at eye level.
   - `?` and `!` are centred over the head.
   - Use the engine (`Pose().body(...)`) only for beats of your own.
4. **Wire.**
   - In `desktop/renderer/renderer.js`, add `<SET>_STATES` and the agent in `ART`.
   - Add a test in `desktop/test/agent-products.test.js`.

## Cheap review loop (follow it, it is the point of this skill)

- Generate: `python tools/<set>_pixel.py`.
- Contract: `python tools/pet_check.py desktop/renderer/assets/<set> <prefix>`. It must print `OK <prefix>: 29/29 states`. Fix what it lists before looking at any picture.
- Visual: **one** contact sheet per batch, with the crab's file in the first row:
  `python tools/pet_sheet.py out.png desktop/renderer/assets/clawd-<x>-v2.svg desktop/renderer/assets/<set>/<prefix>-<x>-v2.svg ... --frames 8 --size 200`.
  Never take one screenshot per frame or per state.
- Tests: `cd desktop && npm test`.
- The other sets' files must stay unchanged; compare checksums before and after.

## Do not

- Do not invent beats when the user says "like Claude": re-skin the crab's file.
- Do not use black outlines, pure red, 5 × 5 blob hands, a face that covers half the body, or clustered closed eyes.
- Do not commit `desktop/renderer/assets/codex/` or `tools/codex_cloud_pixel.py` (gitignored, licensing: `NOTICE.md`).
