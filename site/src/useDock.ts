import { useEffect, useState, type RefObject } from 'react'
import { DOCK_LIFT, dockOffset, feetOf } from './geometry'
import type { Spot } from './phase-view'

const ZERO = { dx: 0, dy: 0 }

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
      if (term) setDock({ dx: Math.min(term.right + 60, window.innerWidth - 60) - feet.x, dy: term.bottom + 14 - feet.y })
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [spot, slotRef, zoneRef, termRef])

  return { dock, setDock }
}
