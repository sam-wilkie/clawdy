import { useEffect, useRef, type RefObject } from 'react'
import { createSpin } from './dizzy'
import { BODY_LIFT, feetOf } from './geometry'
import { DURATION } from './pet-state'

/** Two circles of the pointer around Vinnie make it dizzy (onSpin), then a cooldown before the next one. */
export function useSpinDizzy(enabled: boolean, slotRef: RefObject<HTMLElement | null>, offRef: RefObject<{ dx: number; dy: number }>, onSpin: () => void) {
  const until = useRef(0)
  const spun = useRef(onSpin)
  useEffect(() => { spun.current = onSpin })

  useEffect(() => {
    if (!enabled) return
    const spin = createSpin()
    const onMove = (e: PointerEvent) => {
      const now = performance.now()
      if (now < until.current) { spin.reset(); return }
      const r = slotRef.current?.getBoundingClientRect()
      if (!r) return
      const f = feetOf(r)
      if (spin.push(e.clientX, e.clientY, f.x + offRef.current.dx, f.y + offRef.current.dy - BODY_LIFT, now)) {
        until.current = now + DURATION.dizzy + DURATION.cooldown
        spun.current()
      }
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [enabled, slotRef, offRef])
}
