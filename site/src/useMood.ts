import { useEffect, useState } from 'react'
import type { Phase } from './flow'
import { moodTimeline } from './mood-timeline'

/** Vinnie's mood for the phase, advancing through its beats on timers (undefined when the phase has none). */
export function useMood(phase: Phase) {
  const [at, setAt] = useState({ phase, beat: 0 })
  const beat = at.phase === phase ? at.beat : 0 // a new phase starts from its first beat, no reset effect needed
  const beats = moodTimeline(phase)

  useEffect(() => {
    const ms = moodTimeline(phase)[beat]?.ms
    if (ms === undefined) return
    const id = window.setTimeout(() => setAt({ phase, beat: beat + 1 }), ms)
    return () => window.clearTimeout(id)
  }, [phase, beat])

  return beats[beat]?.mood
}
