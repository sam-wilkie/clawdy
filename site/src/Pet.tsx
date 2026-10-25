import { useCallback, useEffect, useReducer, useRef, useState, type PointerEvent, type ReactNode, type RefObject } from 'react'
import { createSpin } from './dizzy'
import type { Phase } from './flow'
import { contains, dockOffset, dragOffset, feetOf, type Point } from './geometry'
import { DURATION, petReduce } from './pet-state'
import type { Spot } from './phase-view'
import { Vinnie } from './Vinnie'
import type { VinnieState } from './vinnie-states'

const DRAG_THRESHOLD = 6 // px before a press becomes a drag
const BODY_LIFT = 40     // the body centre sits this far above the feet
const DOCK_LIFT = 40     // Vinnie's feet rest this far above the bottom of the drop zone

export interface DragInfo { dragging: boolean; over: boolean }
const NO_DRAG: DragInfo = { dragging: false, over: false }
const ZERO = { dx: 0, dy: 0 }

interface Props {
  phase: Phase
  spot: Spot
  slotRef: RefObject<HTMLDivElement | null>
  zoneRef: RefObject<HTMLDivElement | null>
  termRef: RefObject<HTMLDivElement | null>
  forced?: VinnieState
  extra?: ReactNode
  entrance: boolean
  reduced: boolean
  onDrag: (d: DragInfo) => void
  onDrop: () => void
  onPoke: () => void              // a click or tap on Vinnie
  onCenter: (p: Point) => void    // where Vinnie's body is, so the flowers can follow
}

/** Vinnie on the stage: idle life (sleep, wake, happy, dizzy) and drag and drop onto the drop zone. */
export function Pet({ phase, spot, slotRef, zoneRef, termRef, forced, extra, entrance, reduced, onDrag, onDrop, onPoke, onCenter }: Props) {
  const [state, send] = useReducer(petReduce, entrance && !reduced ? 'walking' : 'idle')
  const [off, setOff] = useState(ZERO)
  const [dock, setDock] = useState(ZERO)
  const offRef = useRef(ZERO)
  const [drag, setDrag] = useState<DragInfo>(NO_DRAG)
  const press = useRef<{ id: number; x: number; y: number; moved: boolean; base: typeof ZERO } | null>(null)
  const over = useRef(false)
  const sleepTimer = useRef(0)
  const dizzyUntil = useRef(0)

  const stage = phase === 'stage'
  const docked = spot !== 'rest'
  const o = docked ? dock : stage ? off : ZERO // Vinnie stays where it was dropped, on the stage
  useEffect(() => { offRef.current = off })

  const armSleep = useCallback(() => {
    window.clearTimeout(sleepTimer.current)
    if (reduced || document.hidden) return
    sleepTimer.current = window.setTimeout(() => send('sleep'), DURATION.idle)
  }, [reduced])

  // Timed states return to idle; idle falls asleep after a long quiet spell.
  useEffect(() => {
    const ms = { happy: DURATION.happy, dizzy: DURATION.dizzy, wake: DURATION.wake, walking: DURATION.walking, idle: 0, sleeping: 0 }[state]
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

  // Two circles of the pointer around Vinnie make it dizzy, then a cooldown.
  useEffect(() => {
    if (!stage || reduced || drag.dragging) return
    const spin = createSpin()
    const onMove = (e: globalThis.PointerEvent) => {
      const now = performance.now()
      if (now < dizzyUntil.current) { spin.reset(); return }
      const r = slotRef.current?.getBoundingClientRect()
      if (!r) return
      const f = feetOf(r)
      if (spin.push(e.clientX, e.clientY, f.x + offRef.current.dx, f.y + offRef.current.dy - BODY_LIFT, now)) {
        send('spin')
        dizzyUntil.current = now + DURATION.dizzy + DURATION.cooldown
      }
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [stage, reduced, drag.dragging, slotRef])

  // Docked spots: on the drop zone (typing) or waiting to the right of the terminal. Recomputed on resize.
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

  // Tell the page where Vinnie's body is (not while it waits beside the terminal), so the flowers can follow.
  useEffect(() => {
    if (spot === 'terminal' || phase === 'intro') return
    const slot = slotRef.current?.getBoundingClientRect()
    if (slot) { const f = feetOf(slot); onCenter({ x: f.x + o.dx, y: f.y + o.dy - BODY_LIFT }) }
  }, [o.dx, o.dy, spot, phase, slotRef, onCenter])

  const report = (d: DragInfo) => { setDrag(d); onDrag(d) }

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    if (!stage || e.button > 0) return
    press.current = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, base: off }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    const p = press.current, slot = slotRef.current, zone = zoneRef.current
    if (!p || e.pointerId !== p.id || !slot || !zone) return
    const dx = e.clientX - p.x, dy = e.clientY - p.y
    if (!p.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    p.moved = true
    const feet = feetOf(slot.getBoundingClientRect())
    const next = dragOffset(feet, p.base, { dx, dy }, window.innerWidth, window.innerHeight)
    setOff(next)
    over.current = contains(zone.getBoundingClientRect(), feet.x + next.dx, feet.y + next.dy - BODY_LIFT)
    report({ dragging: true, over: over.current })
  }

  const finish = (e: PointerEvent<HTMLButtonElement>, cancelled: boolean) => {
    const p = press.current
    press.current = null
    if (!p || e.pointerId !== p.id) return
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    const slot = slotRef.current, zone = zoneRef.current
    if (!p.moved) { if (!cancelled) { send('click'); onPoke() } return }
    if (over.current && !cancelled && slot && zone) {
      setDock(dockOffset(feetOf(slot.getBoundingClientRect()), zone.getBoundingClientRect(), DOCK_LIFT))
      setOff(ZERO)
      onDrop()
    }
    over.current = false
    report(NO_DRAG)
  }

  const shown: VinnieState = forced ?? (spot === 'zone' ? 'typing' : drag.dragging ? (drag.over ? 'typing' : 'idle') : state)
  const cls = ['pet', entrance && 'arrive', drag.dragging && 'held'].filter(Boolean).join(' ')

  return (
    <div ref={slotRef} className="pet-slot">
      <div className={cls} style={{ '--dx': `${o.dx}px`, '--dy': `${o.dy}px` } as React.CSSProperties}>
        <Vinnie state={shown} />
        {extra}
        <button
          className="pet-hit"
          type="button"
          tabIndex={stage ? 0 : -1}
          aria-label="Vinnie. Arrástralo a la terminal o pulsa Enter para alegrarlo."
          disabled={!stage}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={(e) => finish(e, false)}
          onPointerCancel={(e) => finish(e, true)}
          onClick={(e) => { if (e.detail === 0 && stage) { send('click'); onPoke() } }}
        />
      </div>
    </div>
  )
}
