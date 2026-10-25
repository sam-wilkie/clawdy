import type { Phase } from './flow'
import type { VinnieState } from './vinnie-states'

/** Where Vinnie stands: free on the stage, docked on the drop zone, or waiting beside the terminal. */
export type Spot = 'rest' | 'zone' | 'terminal'

/** Everything the page derives from the flow phase, in one place. */
export function phaseView(phase: Phase) {
  const asking = phase === 'permission' || phase === 'plead'
  const spot: Spot = phase === 'terminal' ? 'zone' : asking ? 'terminal' : 'rest'
  const mood: VinnieState | undefined = phase === 'permission' ? 'alert' : phase === 'plead' ? 'error' : phase === 'exit' ? 'cool' : undefined
  return {
    intro: phase === 'intro',
    stage: phase === 'stage',
    terminal: phase === 'terminal' || asking,
    asking,
    showcase: phase === 'showcase',
    exit: phase === 'exit',
    petHidden: phase === 'showcase',
    spot,
    mood,
  }
}
