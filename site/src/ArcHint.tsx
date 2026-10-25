import { useEffect, useState, type RefObject } from 'react'
import { feetOf } from './geometry'

const HAND = 'M6 12V5a1.5 1.5 0 0 1 3 0v6V3.5a1.5 1.5 0 0 1 3 0V11V4.5a1.5 1.5 0 0 1 3 0V11.5V6.5a1.5 1.5 0 0 1 3 0V15c0 4-2.6 6.5-6.5 6.5h-1.2c-2.4 0-3.9-1.1-5.1-2.9L2.4 14c-.6-1 .2-2.2 1.3-1.9L6 13z'

/** A dashed arc with a hand sliding along it, from Vinnie to the drop zone. */
export function ArcHint({ show, petRef, zoneRef }: { show: boolean; petRef: RefObject<HTMLElement | null>; zoneRef: RefObject<HTMLElement | null> }) {
  const [path, setPath] = useState<{ d: string; end: { x: number; y: number }; angle: number } | null>(null)

  useEffect(() => {
    if (!show) return
    const compute = () => {
      const pet = petRef.current, zone = zoneRef.current
      if (!pet || !zone) return
      const feet = feetOf(pet.getBoundingClientRect())
      const a = { x: feet.x - 30, y: feet.y - 40 }
      const z = zone.getBoundingClientRect()
      const b = { x: (z.left + z.right) / 2 + 12, y: z.top - 8 }
      const c = { x: Math.min(a.x, b.x) - 40, y: Math.min(a.y, b.y) - Math.abs(a.x - b.x) * 0.25 - 40 }
      // tangent at the end of the quadratic Bezier is b - c
      setPath({ d: `M${a.x} ${a.y} Q${c.x} ${c.y} ${b.x} ${b.y}`, end: b, angle: Math.atan2(b.y - c.y, b.x - c.x) * 180 / Math.PI })
    }
    compute()
    window.addEventListener('resize', compute)
    return () => window.removeEventListener('resize', compute)
  }, [show, petRef, zoneRef])

  if (!show || !path) return null
  return (
    <svg className="arc-hint" aria-hidden="true" focusable="false">
      <path d={path.d} className="arc-path" />
      <polygon points="3,0 -9,-6 -9,6" className="arc-arrow" transform={`translate(${path.end.x} ${path.end.y}) rotate(${path.angle})`} />
      <g className="arc-hand" style={{ offsetPath: `path('${path.d}')` }}>
        <path d={HAND} transform="translate(-9 -2)" />
      </g>
    </svg>
  )
}
