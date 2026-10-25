import { useEffect, useState } from 'react'
import type { Phase } from './flow'
import { moodTimeline } from './mood-timeline'
import type { TerminalStage } from './terminal-script'

/** Vinnie's mood for the phase, advancing through its beats on timers (undefined when the phase has none). */
export function useMood(phase: Phase, stage?: TerminalStage, compact = false) {
  const key = `${phase}:${stage ?? ''}:${compact}`
  const [at, setAt] = useState({ key, beat: 0 })
  const beat = at.key === key ? at.beat : 0 // a new phase or step starts from its first beat, no reset effect needed
  const beats = moodTimeline(phase, stage, compact)

  useEffect(() => {
    const ms = moodTimeline(phase, stage, compact)[beat]?.ms
    if (ms === undefined) return
    const id = window.setTimeout(() => setAt({ key, beat: beat + 1 }), ms)
    return () => window.clearTimeout(id)
  }, [key, phase, stage, compact, beat])

  return beats[beat]?.mood
}
