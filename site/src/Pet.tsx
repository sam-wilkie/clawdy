import { useEffect, useRef, useState, type PointerEvent, type RefObject } from 'react'
import { createShake } from './dizzy'
import type { Phase } from './flow'
import { BODY_LIFT, DOCK_LIFT, contains, dockOffset, dragOffset, feetOf } from './geometry'
import { DURATION } from './pet-state'
import type { Spot } from './phase-view'
import { useDock } from './useDock'
import { usePetLife } from './usePetLife'
import { useSpinDizzy } from './useSpinDizzy'
import { Vinnie } from './Vinnie'
import type { VinnieState } from './vinnie-states'

const DRAG_THRESHOLD = 6 // px before a press becomes a drag

export interface DragInfo { dragging: boolean; over: boolean }
const NO_DRAG: DragInfo = { dragging: false, over: false }
const ZERO = { dx: 0, dy: 0 }

interface Props {
  phase: Phase
  spot: Spot
  behind: boolean                 // under the terminal window in z-order, while Vinnie slips behind it
  slotRef: RefObject<HTMLDivElement | null>
  zoneRef: RefObject<HTMLDivElement | null>
  termRef: RefObject<HTMLDivElement | null>
  forced?: VinnieState
  entrance: boolean
  reduced: boolean
  onDrag: (d: DragInfo) => void
  onDrop: () => void
  onPoke: () => void              // a click or tap on Vinnie
}

/** Vinnie on the stage: idle life (sleep, wake, happy, dizzy) and drag and drop onto the drop zone. */
export function Pet({ phase, spot, behind, slotRef, zoneRef, termRef, forced, entrance, reduced, onDrag, onDrop, onPoke }: Props) {
  const { state, send, dizzy } = usePetLife(entrance, reduced)
  const [off, setOff] = useState(ZERO)
  const offRef = useRef(ZERO)
  const { dock, setDock } = useDock(spot, slotRef, zoneRef, termRef)
  const [drag, setDrag] = useState<DragInfo>(NO_DRAG)
  const [shake] = useState(createShake)
  const press = useRef<{ id: number; x: number; y: number; moved: boolean; base: typeof ZERO; lastX: number } | null>(null)
  const over = useRef(false)

  const stage = phase === 'stage'
  const o = spot !== 'rest' ? dock : stage ? off : ZERO // Vinnie stays where it was dropped, on the stage
  useEffect(() => { offRef.current = off })
  useSpinDizzy(stage && !reduced && !drag.dragging, slotRef, offRef, () => dizzy(DURATION.dizzy))

  const report = (d: DragInfo) => { setDrag(d); onDrag(d) }

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    if (!stage || e.button > 0) return
    shake.reset()
    press.current = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, base: off, lastX: e.clientX }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    const p = press.current, slot = slotRef.current, zone = zoneRef.current
    if (!p || e.pointerId !== p.id || !slot || !zone) return
    const dx = e.clientX - p.x, dy = e.clientY - p.y
    const step = e.clientX - p.lastX
    p.lastX = e.clientX
    if (!p.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    p.moved = true
    // Shaking Vinnie while dragging makes it dizzy, like the desktop pet.
    if (!reduced && shake.push(step, performance.now())) dizzy(DURATION.dizzyShake)
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

  const shown: VinnieState = forced ?? (spot === 'zone' ? 'typing' : drag.dragging ? (state === 'dizzy' ? 'dizzy' : drag.over ? 'typing' : 'idle') : state)
  const jumping = forced === 'jump' // the hop from the peek spot to the resting spot, an arc in CSS
  const cls = ['pet', entrance && 'arrive', drag.dragging && 'held', jumping && 'jumping'].filter(Boolean).join(' ')

  return (
    <div ref={slotRef} className={`pet-slot${behind ? ' behind' : ''}${jumping ? ' jumping' : ''}`}>
      <div className={cls} style={{ '--dx': `${o.dx}px`, '--dy': `${o.dy}px` } as React.CSSProperties}>
        <Vinnie state={shown} follow={!reduced} />
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
