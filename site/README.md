# Clawdy site

The Clawdy landing: a React page where Vinnie, the desk pet, walks you through a fake coding session.
Vite, React 19, TypeScript, plain CSS. Copy is Spanish; code and comments are English.

```bash
pnpm install
pnpm dev --host 127.0.0.1   # http://127.0.0.1:5173/
pnpm test                   # vitest, pure logic only
pnpm build                  # tsc -b + vite build into dist/
```

The intro plays on every load, like the reference. `?intro=0` skips it (handy while developing) and `prefers-reduced-motion` skips it too.

## Flow

`intro` -> `stage` -> drag Vinnie onto the drop zone -> `terminal` -> `permission` -> Allow opens the `showcase`
page; Deny once shows Vinnie's error animation and a plea (`plead`), Deny twice ends in `exit`. "Volver a empezar" goes back to the start screen (the intro; straight to `stage` with `?intro=0` or reduced motion).
The phases and their transitions live in `src/flow.ts`; `src/phase-view.ts` derives what each phase shows.

## Layout

- `src/flow.ts`, `phase-view.ts`, `pet-state.ts`, `dizzy.ts`, `geometry.ts`, `flower-field.ts`, `intro-schedule.ts`,
  `terminal-script.ts`, `showcase-data.ts`: pure logic, each with a test.
- `src/*.tsx`, `use*.ts`: components and hooks (intro, pet, terminal, permission card, showcase, exit).
- `public/vinnie/*.svg`: Vinnie's animations, copied from `desktop/renderer/assets/monster/`.
  `src/vinnie-states.ts` lists them with their viewBox, and its test checks both against the files.

## Notes

- Name pure modules in kebab-case (`flower-field.ts`, not `flowers.ts`): on Windows `flowers.ts` and `Flowers.tsx`
  are the same path to TypeScript and Vite.
- Colors: Vinnie red `#DE4553`, ink `#0A0A0A`, black, and snow `#FAFAFA` (the Wilkiedevs off-white). Tokens are in `src/index.css`.
- The flow and geometry follow https://clawdondesk.com, observed with REA and Playwright. Its code and art are AGPL-3.0
  and are not used here.
