# Desktop pet art bible

Rules for every pet set of the Electron desktop pet (`desktop/renderer`). The crab (Claude) is the reference; the cloud (Codex, local only) and the brand monster (default pet) follow it. Read this before drawing a new pet. It is written so a new set can be made in a few short iterations instead of many redraws. Agents load the short version as the `new-pet` skill (`.agents/skills/new-pet/SKILL.md`, also exposed to Claude Code in `.claude/skills/new-pet/`).

## 1. Canvas and size

| Item | Value |
|---|---|
| Art pixel | 1 art px = 0.5 SVG unit; art lives in `<g transform="scale(.5)">` |
| Body box | 30 × 32 art px, centre x = 15 |
| Ground | the body rests on row y = 29; shadow on rows 30–31 (black, 30 % and 15 %) |
| viewBox | `-15 -25 45 45` for every state, except `happy` (`-12 -15 40 40`) and `sleeping` (`-10 -20 40 40`). The renderer uses the crab's viewBox per state (`STATES` in `renderer.js`), so a file's viewBox must match it. |
| On screen | the pet box is 180 px, so 1 art px = 2 CSS px. Judge every design at 180 px, not zoomed. |
| Head room | props may go up to y = −50 art px (the top of the viewBox) |

## 2. Pixel rules

- Whole pixels only. Poses and props move in whole art pixels; no anti-aliasing. Smooth motion is allowed only as translate interpolation between whole-pixel poses (the engine's `Smooth`). Rotation and scale come only from the crab's own files when a set re-skins them (section 5).
- 1 px **tonal** outline around every shape: a darker shade of the fill (crab: brown on orange; monster: plum on white, dark red on red), not black.
- Light from the top left: light band on the top/left rim, shade on the bottom/right rim.
- One hue family per body (two at most, like the monster's white/red), plus neutrals. Saturation stays moderate: no pure red, no pure black ink on large areas.
- No stray tip pixels on the silhouette (remove pixels with one 4-neighbour or fewer).
- Visual weight: a new pet should cover about the crab's area at 180 px. A round 30 × 30 body looks too big; Vinnie is shown at 80 % by CSS (`#crab[data-art="monster"] #crab-art { scale: 0.8; }`). A new set should be drawn at its final size (about 24 px across) rather than scaled, so its pixels stay whole.
- Leave flat body area around the face. A face that covers half the body reads as noise at 180 px.

## 3. Character parts

| Part | Rule |
|---|---|
| Eyes | Readable at 180 px. Open eyes keep the brand arrangement (the monster's three eyes touch in one arched row). A 2 × 2 catch-light shows the gaze and moves with it. |
| Closed eyes | Spread apart, one soft curve each. A clustered row of closed lids looks odd. |
| Mouth | Small, just under the eyes. Expressions change the eyes first, then the mouth. |
| Blush | Two 3 × 2 patches at mouth height, only on friendly states. |
| Hands | Floating mittens of 8 × 7 px with a thumb lobe and a crease. White mitten on the left, red on the right (monster). A 5 × 5 blob reads as a stray pixel. |
| Error eyes | The crab's bold 6 × 6 X, with no eye ring, and a flat mouth (X_X). |

## 4. States

A set ships one file per state: `desktop/renderer/assets/<set>/<prefix>-<state>-v2.svg`. The 29 states are the keys of `STATES` in `renderer.js` plus `alert` (urgent: needs approval or an answer; gentler than it is `notification`).

| State | Loop | Route used by the monster |
|---|---|---|
| idle | 20 s | engine (cloud beats) |
| waiting_reply, error, happy, alert | 2 s, 2.4 s, 2 s, 4 s | engine, crab beats |
| beacon, debugger, thinking, disconnected, low_battery, sweeping, sleeping, wizard, hat_mishap, cool | crab timing | crab re-skin |
| building | 3 s | own (welding a beam) |
| typing, conducting, juggling, grooving, confused, dizzy, idea, notification, walking, going_away, wake, mini_clawd, no_credits | engine | engine (cloud beats) |

**Props that sit on the head** (hats, antennas, battery, bubbles, ?, !) move up by the difference between the crab's head top (y = 12) and the new head top: −10 px for the monster, −6 px for hats, whose brim sits just above the eyes.

**Prop rules learned from review:**
- A hat is as wide as the head (the monster's: 32 px), with its brim at eye level.
- The `?` and `!` marks are centred over the head.
- The magnifier lens covers a whole eye.
- `building` shows real construction work (welding, tools), not stacked blocks that look like toys.
- When the request says "like Claude", re-skin the crab's file (section 5) instead of inventing new beats.

## 5. Three ways to make a state

1. **Crab re-skin** (preferred when the state should look like Claude's). `tools/crab_skin.py` rewrites the crab file's `<defs>`:
   - legs are emptied;
   - `torso*` becomes the new body and its mouth;
   - `arm-*` becomes a mitten centred where the pincer was;
   - eye groups become the new eyes;
   - head props get a translate.

   The scene and the CSS timing stay the crab's. See `crab_skin()` in `tools/monster_pixel.py`.
2. **Engine poses** (`tools/codex_cloud_pixel.py`, local only). A pose function per frame (`Pose().body(...)`, layer key → whole-pixel position), turned into step-end opacity tracks and smooth translates. Use it for beats of your own.
3. **Own renderer** in the set's generator, built on the engine, for a new idea (the monster's welding `building`).

## 6. Workflow (cheap in tokens)

1. **Static mockup first.** Draw one PNG with the crab beside the candidate at 180 px and at 2×, plus two or three expressions. Get approval before animating; a redraw of 29 animations costs far more than a mockup.
2. **Generate.** Run `python tools/<set>_pixel.py`. Generation must be deterministic (two runs give the same bytes).
3. **Review with one contact sheet per batch**, not one screenshot per frame. `python tools/pet_sheet.py out.png <svg> [<svg> ...] --frames 8 --size 200` gives one row per file. Put the crab's file in the first row to compare.
4. **Live check.** Start a second pet that does not touch the real one: run `CLAWDY_PORT=19873 desktop/node_modules/electron/dist/electron.exe desktop`, then `CLAWDY_PORT=19873 node desktop/fake-daemon.js vinnie`. Kiro, OpenCode and Antigravity each show Vinnie in a different state, rotating every 6 s.
5. **Gallery.** `desktop/renderer/assets/<set>/compare-v2.html` shows Claude, Codex and the set side by side.
6. **Checks.**
   - `python tools/pet_check.py desktop/renderer/assets/<set> <prefix>`: checks the 29 files, each file's viewBox against the renderer, and that every coordinate is a whole art pixel. It is cheap, so run it before looking at any picture.
   - `cd desktop && pnpm test`: the art-selection tests also check that every referenced file exists.
   - The other sets' files are unchanged.
7. **Wire a new set.**
   - Map the agent to the set in `renderer.js` (`ART`, `<SET>_STATES`).
   - If the set paints its own idle, hide the inline crab with `#crab:not([data-art="crab"]) #crab-idle`.
   - Add a test in `desktop/test/agent-products.test.js`.

## 7. Sets today

| Set | Files | Generator | Used by |
|---|---|---|---|
| crab | `assets/clawd-*-v2.svg` | hand-made / svgbuild | claude |
| cloud | `assets/codex/cloud-*-v2.svg` (gitignored, licensing: `NOTICE.md`) | `tools/codex_cloud_pixel.py` (gitignored) | codex |
| monster (**Vinnie**, character sheet: `docs/vinnie.md`) | `assets/monster/monster-*-v2.svg` | `tools/monster_pixel.py` (needs the local cloud engine) | every other agent |
