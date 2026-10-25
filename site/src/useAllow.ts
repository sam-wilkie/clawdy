import { useEffect, useRef, useState } from 'react'
import type { Phase } from './flow'

/** ms: the permission card fades, then the terminal shrinks away with Vinnie, then the showcase opens (the reference's timing). */
export const ALLOW = { card: 400, stage: 500 }

/**
 * The allow choreography while the phase is 'allowing': 'card' (the card fades) then 'stage' (the terminal shrinks and
 * Vinnie fades), then onDone. Under reduced motion there is nothing to watch, so it finishes at once.
 */
export function useAllow(phase: Phase, reduced: boolean, onDone: () => void) {
  const [stage, setStage] = useState(false)
  const finish = useRef(onDone)
  useEffect(() => { finish.current = onDone }) // the latest callback, without restarting the timers on every render

  useEffect(() => {
    if (phase !== 'allowing') return
    if (reduced) { finish.current(); return }
    const toStage = window.setTimeout(() => setStage(true), ALLOW.card)
    const done = window.setTimeout(() => finish.current(), ALLOW.card + ALLOW.stage)
    return () => { window.clearTimeout(toStage); window.clearTimeout(done); setStage(false) }
  }, [phase, reduced])

  return phase === 'allowing' && stage
}
