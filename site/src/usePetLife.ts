import { useCallback, useEffect, useReducer, useRef } from 'react'
import { DURATION, petReduce } from './pet-state'

/** Vinnie's idle life: a state machine with timed states, falling asleep when left alone and waking on any activity. */
export function usePetLife(entrance: boolean, reduced: boolean) {
  const [state, send] = useReducer(petReduce, entrance && !reduced ? 'walking' : 'idle')
  const dizzyMs = useRef<number>(DURATION.dizzy)
  const sleepTimer = useRef(0)

  const armSleep = useCallback(() => {
    window.clearTimeout(sleepTimer.current)
    if (reduced || document.hidden) return
    sleepTimer.current = window.setTimeout(() => send('sleep'), DURATION.idle)
  }, [reduced])

  // Timed states return to idle; idle falls asleep after a long quiet spell.
  useEffect(() => {
    const ms = { happy: DURATION.happy, dizzy: dizzyMs.current, wake: DURATION.wake, walking: DURATION.walking, idle: 0, sleeping: 0 }[state]
    if (reduced || !ms) return
    const id = window.setTimeout(() => send('settle'), ms)
    return () => window.clearTimeout(id)
  }, [state, reduced])
  useEffect(() => { if (state === 'idle') armSleep() }, [state, armSleep])
  useEffect(() => () => window.clearTimeout(sleepTimer.current), [])

  // Any activity wakes Vinnie and re-arms the sleep timer.
  useEffect(() => {
    const activity = () => { send('activity'); armSleep() }
    window.addEventListener('pointermove', activity, { passive: true })
    window.addEventListener('pointerdown', activity, { passive: true })
    window.addEventListener('keydown', activity)
    document.addEventListener('visibilitychange', armSleep)
    return () => {
      window.removeEventListener('pointermove', activity)
      window.removeEventListener('pointerdown', activity)
      window.removeEventListener('keydown', activity)
      document.removeEventListener('visibilitychange', armSleep)
    }
  }, [armSleep])

  /** Make Vinnie dizzy for ms (circling pointer: 6 s, shaking while dragged: 2 s). */
  const dizzy = useCallback((ms: number) => { dizzyMs.current = ms; send('spin') }, [])
  return { state, send, dizzy }
}
