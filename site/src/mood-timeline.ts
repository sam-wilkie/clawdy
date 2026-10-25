import type { Phase } from './flow'
import type { TerminalStage } from './terminal-script'
import type { VinnieState } from './vinnie-states'

/** One beat of Vinnie's mood: how long it lasts in ms; a beat without ms holds until the phase ends. */
export interface Beat { mood: VinnieState; ms?: number }

/**
 * What Vinnie shows over time while the permission card is up. When the card arrives a bulb lights up, then it waits;
 * after a Deny it shows the error, wakes up and waits for another answer, instead of staying in the error.
 */
export function moodTimeline(phase: Phase, stage?: TerminalStage, compact = false): Beat[] {
  if (phase === 'terminal' && (stage === 'think' || stage === 'tool')) {
    if (compact) return [{ mood: 'walking', ms: 700 }]
    // think: walk to the window's left edge, slip under it; tool: cross hidden under the window, peek out at the right
    // edge (look left, right, up, blink: 1.8 s sprite), slip out
    return stage === 'think'
      ? [{ mood: 'walking', ms: 650 }, { mood: 'slip_in' }]
      : [{ mood: 'slip_in', ms: 650 }, { mood: 'peek', ms: 1800 }, { mood: 'slip_out' }]
  }
  switch (phase) {
    case 'permission': return [{ mood: 'idea', ms: 2400 }, { mood: 'waiting_reply' }]
    case 'plead': return [{ mood: 'error', ms: 2200 }, { mood: 'wake', ms: 1600 }, { mood: 'waiting_reply' }]
    default: return []
  }
}

/** The mood after `elapsed` ms, or undefined when there are no beats. */
export function moodAt(beats: Beat[], elapsed: number): VinnieState | undefined {
  let t = 0
  for (const b of beats) {
    if (b.ms === undefined || elapsed < t + b.ms) return b.mood
    t += b.ms
  }
  return beats.at(-1)?.mood
}
