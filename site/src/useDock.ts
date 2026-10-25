import { useEffect, useState, type RefObject } from 'react'
import { DOCK_LIFT, dockOffset, feetOf, type Point } from './geometry'
import type { Spot } from './phase-view'

const ZERO = { dx: 0, dy: 0 }

/**
 * Next to the terminal window, in the place the slip sprites were drawn for (S = Vinnie's box in px): to slip in he stands
 * just left of the left edge (0.189 S, the edge is at viewBox x = 16); to slip out his resting spot is just right of the
 * right edge (0.167 S, the edge is at viewBox x = 0), kept on screen. Feet sit a little above the window's bottom.
 */
function windowSpot(spot: 'hide' | 'terminal', feet: Point, term: DOMRect, S: number) {
  const x = spot === 'hide' ? term.left - 0.189 * S : Math.min(term.right + 0.167 * S, window.innerWidth - 0.3 * S)
  return { dx: x - feet.x, dy: term.bottom - 20 - feet.y }
}

/**
 * Where Vinnie goes when it is docked: on the drop zone (typing) or waiting to the right of the terminal.
 * Recomputed on resize. setDock lets a drop write the zone spot at once, before the phase changes.
 */
export function useDock(spot: Spot, slotRef: RefObject<HTMLElement | null>, zoneRef: RefObject<HTMLElement | null>, termRef: RefObject<HTMLElement | null>) {
  const [dock, setDock] = useState(ZERO)

  useEffect(() => {
    if (spot === 'rest') return
    const place = () => {
      const slot = slotRef.current?.getBoundingClientRect()
      if (!slot) return
      const feet = feetOf(slot)
      if (spot === 'zone') {
        const zone = zoneRef.current?.getBoundingClientRect()
        if (zone) setDock(dockOffset(feet, zone, DOCK_LIFT))
        return
      }
      const term = termRef.current?.getBoundingClientRect()
      if (term) setDock(windowSpot(spot, feet, term, slot.width))
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [spot, slotRef, zoneRef, termRef])

  return { dock, setDock }
}
