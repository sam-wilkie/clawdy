import { VINNIE, type VinnieState } from './vinnie-states'

/** Vinnie as an <img> of its animated SVG, placed so every state shares one pixel scale (viewBox ratio and offset). */
export function Vinnie({ state, replay = 0, className }: { state: VinnieState; replay?: number; className?: string }) {
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
