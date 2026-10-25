import { useCallback, useEffect, useState } from 'react'
import type { DragInfo } from './Pet'

const ARC_DELAY = 3000 // ms on the stage before the dashed arc shows the way
const NO_DRAG: DragInfo = { dragging: false, over: false }

/** What the visitor has done on the stage: dragging, ever dragged, poked (click or drag) and whether the arc hint is due. */
export function useStageActivity(stage: boolean, reduced: boolean) {
  const [drag, setDrag] = useState<DragInfo>(NO_DRAG)
  const [dragged, setDragged] = useState(false)
  const [bloomed, setBloomed] = useState(false) // the first click or drag makes the flowers bloom
  const [arcReady, setArcReady] = useState(false)

  useEffect(() => {
    if (!stage || dragged || reduced) return
    const id = window.setTimeout(() => setArcReady(true), ARC_DELAY)
    return () => window.clearTimeout(id)
  }, [stage, dragged, reduced])

  const onDrag = useCallback((d: DragInfo) => {
    setDrag(d)
    if (d.dragging) { setDragged(true); setBloomed(true) }
  }, [])
  const poke = useCallback(() => setBloomed(true), [])
  const reset = useCallback(() => { setDrag(NO_DRAG); setDragged(false); setBloomed(false); setArcReady(false) }, [])

  return { drag, dragged, bloomed, arcReady, onDrag, poke, reset }
}
