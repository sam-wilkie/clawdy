import { useEffect, useState } from 'react'
import { FADE_MS, crossfade, settle } from './crossfade'
import { GazeSprite } from './GazeSprite'
import { VINNIE, type VinnieState } from './vinnie-states'

interface Props { state: VinnieState; replay?: number; className?: string; follow?: boolean }

/** One state as an <img> of its animated SVG, placed so every state shares one pixel scale (viewBox ratio and offset). */
function Sprite({ state, replay = 0, className, follow }: Props) {
  // The idle sprite is inlined when its face should follow the pointer; every other state is an <img>.
  if (state === 'idle' && follow !== undefined) return <GazeSprite follow={follow} />
  const { src, vb } = VINNIE[state]
  const size = vb[2] / 45 * 100
  return (
    <img
      className={className}
      // An SVG in <img> keeps its own timeline: a new query string restarts a one-shot state.
      src={replay ? `${src}?play=${replay}` : src}
      alt=""
      draggable={false}
      style={{
        position: 'absolute',
        width: `${size}%`,
        height: `${size}%`,
        left: `${(15 + vb[0]) / 45 * 100}%`,
        top: `${(25 + vb[1]) / 45 * 100}%`,
        imageRendering: 'pixelated',
        maxWidth: 'none',
        pointerEvents: 'none',
      }}
    />
  )
}

/**
 * Vinnie in `state`. A change of state crossfades (FADE_MS): the previous sprite stays mounted fading out while the new
 * one fades in, so the swap is never a hard cut. Keys are the state names, so a sprite is never remounted (and its
 * one-shot timeline never restarted) when the fade ends.
 */
export function Vinnie({ state, ...rest }: Props) {
  const [fade, setFade] = useState(() => crossfade(undefined, state))
  const next = crossfade(fade, state)
  if (next !== fade) setFade(next) // derived during render: the sprite that was showing becomes `leaving`

  useEffect(() => {
    if (!next.leaving) return
    const id = window.setTimeout(() => setFade((f) => (f.leaving ? settle(f) : f)), FADE_MS)
    return () => window.clearTimeout(id)
  }, [next])

  return (
    <>
      {next.leaving && <div key={next.leaving} className="sprite out"><Sprite state={next.leaving} follow={rest.follow} /></div>}
      <div key={next.cur} className={next.leaving ? 'sprite in' : 'sprite'}><Sprite state={next.cur} {...rest} /></div>
    </>
  )
}
