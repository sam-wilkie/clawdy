import type { VinnieState } from './vinnie-states'

/** How long one sprite fades out while the next fades in (ms): hides the hard cut between two SVGs. */
export const FADE_MS = 140

export interface Fade { cur: VinnieState; leaving?: VinnieState }

/** The fade after the shown state becomes `next`: the previous sprite leaves, and an older one still leaving is dropped. */
export function crossfade(f: Fade | undefined, next: VinnieState): Fade {
  if (!f) return { cur: next }
  return f.cur === next ? f : { cur: next, leaving: f.cur }
}

/** The fade once the leaving sprite is gone. */
export const settle = (f: Fade): Fade => ({ cur: f.cur })
