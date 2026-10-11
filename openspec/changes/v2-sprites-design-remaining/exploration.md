# Exploration: Design the 7 missing v2 crab SVGs, then port all 7 to firmware in one batch

Status: complete · Artifact store: openspec · Engram: `sdd/v2-sprites-design-remaining/explore` (id 3512)
Builds on archived `v2-sprites-on-device` and `openspec/specs/device-v2-sprites/spec.md`.

## Goal

Design the 7 missing v2 crab animation SVGs (beacon, wizard, juggling, walking, going_away,
disconnected, mini_crab), get them visually approved, then port all 7 to the ESP32-C6 firmware
together in one batch using the proven pipeline.

## Current State

The device port pipeline for v2 sprites is PROVEN and parametrized. 15 anims that already had v2
SVGs were ported. The 7 target anims all still render v1 art. All 7 HAVE a v1 SVG, but in the OLD
flat style (viewBox `-15 -25 45 45`, 1 unit = 1 art px, flat `#DE886D` rects, using
`rotate()`/`scale()`/SMIL) — none legal in the v2 rig. The v2 redesign must re-express the MOTION,
not port the markup.

## 1. v2 SVG style contract (design bible)

Authoritative: the header comment in `assets/svg-animations/clawd-static-base-v2.svg`.
- viewBox/size: base `0 0 15 16` (w300 h320); animated files widen (happy `-12 -15 40 40`,
  debugger/wake `-15 -25 45 45`, w/h 500). Rendered at `--scale 3 --snap exact`.
- Grid: 1 art px = 0.5 SVG unit; body box 30×32 art px; all art inside `<g transform="scale(.5)">`
  in integer art px. WHOLE ART PIXELS ONLY — no rotation, no scaling, no fractional moves. This bans
  v1's rotate/scale/SMIL motion.
- Palette: outline `#6B3122`, base `#DE886D`, light `#F3AC90`, specular `#FFD3C2`, shade `#B8644B`,
  eyes `#1B1311`+white, blush `#EA7C7E`/`#F7A3A1`; props (hat/wood/steel/spark) + shadow (black 30%+15%).
- Shading: 1px inner outline; light top-left; eye variants open 2×4 / shut 2×1 / wide 2×5 / happy arc / squint 2×2.
- Shared rig `<defs>` copied verbatim per file: shadow(s), leg1..4, torso, arm-l/arm-r (rest/slide,
  dy -3..3), arm-l-free/arm-r-free (+4-row forearm when raised), eyes variants, blush, smile.
- Tech: CSS `@keyframes` with `step-end` ONLY (no SMIL, no easing); one keyframe per rendered frame;
  motion = whole-px `translate` on `<g class>` wrapping `<use>`; variant swaps via opacity 0/1.
- Cost: ~300–500 lines/anim.

## 2. The 7 anims — v1 ref, intent, specialness

Terminal poses exist only for beacon, wizard, juggling. walking/going_away/disconnected/mini_crab
have NO terminal pose (device/web-only).
1. beacon — antenna + blinking tip + expanding/fading rings, body bob (LOOP). SMIL rings → opacity-swapped expanding pixel outlines.
2. wizard — crooked hat (reuse the already-v2 hat from clawd-hat-mishap-v2.svg), wand + glowing tip, float, rising stars (LOOP). rotate → discrete arm positions.
3. juggling — 3 packets on parabolic arcs, eyes dart, body rock (LOOP; daemon-retired, kept for /margarita). sin/rotate → per-frame whole-px positions.
4. walking — sideways walk cycle, alternating legs, bob (LOOP). Device layers a slide-in on top (walk_in_complete_cb, scene.c:559); sprite needs only the in-place cycle.
5. going_away — frantic dig + burrow down, dirt, hole, ground-clipped (ONESHOT, session exit). HARDEST: v1 clipPath + CSS-var dirt → discrete y-sink + opacity dirt + sink below static grass line; last-frame-hold = crab gone.
6. disconnected — look-around + "?" then spots BLE icon + "!" (LOOP). Defines the device 73 KB heap peak (182×137); v2 will likely shrink it, lowering the ceiling.
7. mini_crab — SPECIAL tiny HUD subagent-counter icon (~10×7). Not a grass crab.

## 3. Device naming / fps / looping (current v1, scene.c:149+)

Name mismatches: WALKING←`clawd-crab-walking`, MINI_CLAWD→prefix `mini_crab`←`clawd-mini-clawd`,
BEACON/WIZARD/JUGGLING←`clawd-working-*`.

| anim | fps / FRAME_MS | looping | v1 y_offset |
|---|---|---|---|
| disconnected | 6 / 167 | true | -6 (182×137 = 73KB peak) |
| juggling | 8 / 125 | true | -8 |
| walking | 8 / 125 | true | -8 |
| going_away | 8 / 125 | **false (oneshot)** | -6 |
| wizard | 8 / 125 | true | -8 |
| beacon | 8 / 125 | true | +4 |
| mini_crab | 4 / 250 | true | -5 (HUD-blit, not a slot) |

Only going_away is a oneshot. The 6 grass crabs will likely converge to ~-21 (GRASS_HEIGHT=24,
0 bottom-transparent rows) — confirm each visually.

## 4. mini_crab handling

Same png2rgb565+crop pipeline for generation, BUT consumed by `hud_blit_mini_crab()` (scene.c:1655)
which decodes ARGB8888 and per-pixel blits to a canvas at integer upscale — bypassing anim_defs
y_offset/grass. The "ground-aligned on 320×172" spec requirement does NOT apply. Heap negligible.
OPEN DECISION for proposal: animated micro-crab vs scaled v2 static base icon.

## 5. Porting path (all 7 together)

`py -3.11 tools/regen_v2_sprite.py <prefix> <svg> <fps> --scale 3` (driver exists). width/height/
frame_count auto-flow from header macros; hand-edits = y_offset (crop delta) + FRAME_MS if fps
changes; preserve `.looping` (going_away false). scene.h/clawd_sprites.h untouched.

Test harness: move the 7 from `V1_UNTOUCHED_PREFIXES` into `PORTED_PREFIXES`+`PORTED_FPS` (15→22).
After the move `V1_UNTOUCHED_PREFIXES` becomes EMPTY — the no-regression test loses its subjects
(remove or repurpose). frame_ms sim capture may not cover mini_crab's HUD-blit path — flag.

Anims that don't fit the standard grass-sprite pipeline: mini_crab (HUD blit), going_away (oneshot
burrow / "gone" end state — watch crop of empty frames), walking (device slide-in layered on top),
disconnected (defines heap ceiling).

## 6. Risks

- Authoring feasibility (biggest): 7 × ~300–500-line hand-written step-end SVGs; Opus-class can do
  it (the 15 were made this way) but review/iteration cost is high. Split into reviewable sub-batches.
- Motion hard in the v2 rig: going_away burrow+clip+dirt (hardest, a transition not a loop), beacon
  SMIL rings, wizard/juggling rotate+sin arcs — all re-baked as discrete whole-px translates + opacity.
- Flash/heap: in-place replace; v2 RLE ~25–45 KB ≈ v1; disconnected (73KB peak) will shrink → ceiling drops. mini_crab negligible.
- Contract: emptied `V1_UNTOUCHED_PREFIXES` must be handled.

## Recommendation

Two-phase change: (A) Design — hand-author all 7 v2 SVGs in the bible style (reuse shared rig defs +
the already-v2 wizard hat), re-express each v1 motion as step-end whole-px keyframes, browser-review
and approve ALL 7; (B) Port — run regen for all 7 at --scale 3, retune 7 y_offsets (expect ~-21 for
the 6 grass crabs; mini_crab stays HUD-blit), extend PORTED_PREFIXES 15→22, preserve going_away
oneshot, simulator visual-gate each, resolve the emptied no-regression test. Decide mini_crab design
at proposal time.

Ready for Proposal: Yes.
