# Clawdy site (React)

Rebuild the Clawdy landing as a React app that follows the flow of the reference site, with Vinnie as the pet.
Branch: `feat/site-react` (from `feat/vinnie-pet`). Delivery: ask-on-risk. Runner: `pnpm test` (vitest) in `site/`. Engram mirror: `odd/clawdy-site-react/tasks`.

## Specs

- S1 "como lo mejoramos con react? quiero que sea mas movil": a React app (Vite, pnpm) in a new versioned folder `site/`; mobile first, works at 390 px wide with touch. User confirmed the plan with "hazlo". The old `website/` prototype stays untouched and ignored.
- S2 "estabamos basados en esta pagina ... aun faltan muchas cosas como mi github en la esquina, muchas animaciones, la interfaz de mas correctamente, las posiciones etc...": the flow and positions follow https://clawdondesk.com, observed with REA ("USA https://github.com/morluto/rea para que tengamos el flujo similar") and Playwright on 2026-10-24 at 1280x720.
- S3 Flow observed: intro on a dark screen (Vinnie above, cursor types the wordmark, flash, delete, centre) -> iris opens the desk -> stage (Vinnie, hint pill under it, drop zone bottom-left, dot grid, flower patch) -> drag Vinnie into the drop zone -> terminal window appears -> typed prompt, "thinking", Bash tool, "Do you want to proceed?" with 3 options -> permission card -> Allow opens the second page; Deny makes Vinnie plead once (card text changes, hearts, option 3 selected), a second Deny ends in the exit screen.
- S4 Geometry at 1280x720 (REA screenshot): terminal 562x317 at (359,267), dark, three macOS dots, title "clawd@desk: ~"; behind the permission card the terminal is dimmed and blurred; permission card 359x192 at (806,245): title "Permission Request", pill "BASH", code box, buttons Allow / Deny; Vinnie waits at about (938,541) to the right of the terminal; flower patch bottom-left of the terminal; drop zone 128x149 at (230,488); hint pill about 168x36 under Vinnie; author link bottom-right at (1080,687).
- S5 Second page (Allow): "Clawd on Desk" / "A little company for your coding day." become the Clawdy title and a Spanish subtitle; grid of 6 cards with Vinnie animations and captions Reading, Thinking, Typing, Wizard, 1 Subagent, 2+ Subagents (3 columns on desktop, fewer on phones); "Play from start" button top-right; a GitHub pill at the bottom linking to the repo.
- S6 "mi github en la esquina": a link `github.com/sam-wilkie` fixed bottom-right on every screen, pointing to https://github.com/sam-wilkie/clawdy. Never the original author's link.
- S7 "los Colores deberian ser, el rojo, negro para contraste y blanco no puro" + "el rojo de vinnie en este caso me gusta como mas": Vinnie red `#DE4553`, black `#000000` and ink `#0A0A0A`, snow `#FAFAFA`. Red is for fills and accents; small text stays ink.
- S8 "muchas animaciones": walk-in, happy on click, dizzy after two circles of the pointer, sleep after idle and wake on movement, dashed arc with a hand from Vinnie to the drop zone, flower patch, absorb into the terminal, typed terminal lines and thinking spinner, permission card pop-in, pleading on first Deny, shades on exit, staggered showcase cards. `prefers-reduced-motion` skips the intro and long motion.
- S9 Copy is Spanish (the previous prototype's UI language). Code and comments are English.
- S10 Not copied from the reference: its code and art are AGPL-3.0. Behaviour, geometry and flow are rebuilt from observation; art is Vinnie's SVGs from `desktop/renderer/assets/monster/`.
- S11 Assumption (not asked): no extra menu or header; the "navigation" is the flow itself plus "Play from start" and the GitHub links.

## Tasks

- T1 S1 S7 S9 · scaffold `site/` (Vite + React + TS + vitest), tokens, Vinnie component and assets, flow reducer with tests · inline · RED: both test files failed (modules missing), GREEN: 25 tests · commit: see git log (feat(site) scaffold)
- T2 S2 S3 S6 S8 · intro, stage, drag and drop, dizzy, sleep, arc hint, flowers, GitHub corner · inline · commit: pending
- T3 S3 S4 S8 · terminal, permission card, Allow/Deny with plea · inline · commit: pending
- T4 S5 S3 · showcase page, exit screen, Play from start · inline · commit: pending
- T5 S1 S4 S8 · mobile layout, reduced motion, README/TODO, Playwright check at 390 and 1280 · inline · commit: pending

## Log

- L1 (2026-10-24, user) "porq le faltan tantas funcionalidades a esa pagina? el intro y todo lo demas? como lo mejoramos con react? quiero que sea mas movil y faltan las otras interfaces de navegacion, porq no se ven?"
- L2 (2026-10-24, user) "los Colores deberian ser, el rojo, negro para contraste y blanco no puro, los mismos colores que usa Wilkiedevs.com"
- L3 (2026-10-24, user) "el rojo de vinnie en este caso me gusta como mas, y que paso con la segunda pagina que aparece cuando aceptas la opcion SI? https://clawdondesk.com/ estabamos basados en esta pagina que analisaste con REA pero aun faltan muchas cosas como mi github en la esquina, muchas animaciones, la interfaz de mas correctamente, las posiciones etc..."
- L4 (2026-10-24, user) "hazlo"
- L5 (2026-10-24, user) "USA https://github.com/morluto/rea para que tengamos el flujo similar"
- Route: all tasks inline (no Writer trigger: units are sequential and share the flow state). Risk per task: none expected; T5 touches no existing consumer.
- Evidence: REA `list_browser_targets`, `inspect_web_page` (DOM outline: main.stage with 9 state imgs, terminal block, permission card, section#showcase with 6 figures, CTA link) and `capture_web_screenshot` (terminal stage) over CDP; `capture_browser_scenario` captured the intro but cannot drag, so Playwright drove the drag. License check: `gh api repos/rullerzhou-afk/clawd-on-desk/license` -> AGPL-3.0.
