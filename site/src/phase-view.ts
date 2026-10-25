import type { Phase } from './flow'
import type { TerminalStage } from './terminal-script'
import type { VinnieState } from './vinnie-states'

/** Where Vinnie stands: free on the stage, docked on the drop zone, at the window's left edge to slip in, or beside its right edge. */
export type Spot = 'rest' | 'zone' | 'hide' | 'terminal'

/**
 * Everything the page derives from the flow phase, in one place. While the terminal runs, Vinnie types on the drop zone,
 * slips under the window's left edge while the agent thinks and comes out at its right edge (stage = the terminal's step).
 * compact (a narrow screen or reduced motion) has no edge to hide behind: Vinnie just walks to the waiting spot.
 */
export function phaseView(phase: Phase, stage?: TerminalStage, compact = false) {
  const asking = phase === 'permission' || phase === 'plead'
  const allowing = phase === 'allowing' // Allow was pressed: the card fades, then the terminal shrinks away with Vinnie
  const running = phase === 'terminal' && (stage === 'think' || stage === 'tool')
  const spot: Spot = phase === 'terminal'
    ? running ? (compact || stage === 'tool' ? 'terminal' : 'hide') : 'zone'
    : asking || allowing ? 'terminal' : 'rest'
  const mood: VinnieState | undefined = phase === 'exit' ? 'cool' : undefined
  return {
    intro: phase === 'intro',
    stage: phase === 'stage',
    terminal: phase === 'terminal' || asking || allowing,
    asking,
    allowing,
    showcase: phase === 'showcase',
    exit: phase === 'exit',
    petHidden: phase === 'showcase',
    behind: running && !compact, // under the window in z-order, so the real window hides him as he slides
    spot,
    mood,
  }
}
