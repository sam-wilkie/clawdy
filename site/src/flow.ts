export type Phase = 'intro' | 'stage' | 'terminal' | 'permission' | 'plead' | 'showcase' | 'exit'
export interface Flow { phase: Phase; denies: number }
export type Action =
  | { type: 'introDone' | 'dropped' | 'terminalReady' | 'allow' | 'deny' }
  | { type: 'restart'; intro: boolean } // back to the start: the intro, or the stage when there is no intro

/** The intro plays on every load, like the reference; ?intro=0 skips it and reduced motion never plays it. */
export function wantsIntro(o: { reduced: boolean; skip: boolean }): boolean {
  return !o.reduced && !o.skip
}

export const initialFlow = (intro: boolean): Flow => ({ phase: intro ? 'intro' : 'stage', denies: 0 })

/** One step of the page flow; an action from the wrong phase leaves the state as it was. */
export function reduce(f: Flow, a: Action): Flow {
  switch (a.type) {
    case 'introDone': return f.phase === 'intro' ? { ...f, phase: 'stage' } : f
    case 'dropped': return f.phase === 'stage' ? { ...f, phase: 'terminal' } : f
    case 'terminalReady': return f.phase === 'terminal' ? { ...f, phase: 'permission' } : f
    case 'allow': return f.phase === 'permission' || f.phase === 'plead' ? { ...f, phase: 'showcase' } : f
    case 'deny':
      if (f.phase === 'permission') return { phase: 'plead', denies: f.denies + 1 }
      if (f.phase === 'plead') return { phase: 'exit', denies: f.denies + 1 }
      return f
    case 'restart': return f.phase === 'showcase' || f.phase === 'exit' ? initialFlow(a.intro) : f
  }
}
