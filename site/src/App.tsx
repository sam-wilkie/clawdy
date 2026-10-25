import { useEffect, useReducer, useRef, useState } from 'react'
import { ArcHint } from './ArcHint'
import { Flowers } from './Flowers'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import { markSeen, readSeen } from './intro-schedule'
import { Intro } from './Intro'
import { Pet, type DragInfo } from './Pet'
import { useIntro } from './useIntro'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const forced = new URLSearchParams(window.location.search).get('intro') === '1'
const ARC_DELAY = 3000 // ms on the stage before the dashed arc shows the way

export default function App() {
  const [withIntro] = useState(() => wantsIntro({ reduced, forced, seen: readSeen() }))
  const [flow, dispatch] = useReducer(reduce, withIntro, initialFlow)
  const intro = useIntro(flow.phase === 'intro', () => { markSeen(); dispatch({ type: 'introDone' }) })
  const [drag, setDrag] = useState<DragInfo>({ dragging: false, over: false })
  const [dragged, setDragged] = useState(false)
  const [arcReady, setArcReady] = useState(false)
  const slotRef = useRef<HTMLDivElement>(null)
  const zoneRef = useRef<HTMLDivElement>(null)

  const inIntro = flow.phase === 'intro'
  const stage = flow.phase === 'stage'

  useEffect(() => {
    if (!stage || dragged || reduced) return
    const id = window.setTimeout(() => setArcReady(true), ARC_DELAY)
    return () => window.clearTimeout(id)
  }, [stage, dragged])

  return (
    <main className="stage" data-phase={flow.phase} data-frame={inIntro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <Flowers show={drag.dragging || (!stage && !inIntro)} zoneRef={zoneRef} reduced={reduced} />
      {inIntro && <Intro {...intro} />}
      <div ref={zoneRef} className={`drop-zone${drag.dragging ? ' show' : ''}${drag.over ? ' over' : ''}`} aria-hidden="true">Suéltame aquí</div>
      <ArcHint show={stage && arcReady && !dragged} petRef={slotRef} zoneRef={zoneRef} />
      <Pet
        phase={flow.phase}
        slotRef={slotRef}
        zoneRef={zoneRef}
        forced={inIntro && intro.frame === '3' ? 'alert' : undefined}
        entrance={!withIntro}
        reduced={reduced}
        onDrag={(d) => { setDrag(d); if (d.dragging) setDragged(true) }}
        onDrop={() => dispatch({ type: 'dropped' })}
      />
      {stage && !drag.dragging && <p className="hint" aria-hidden="true">Prueba a arrastrarme</p>}
      <GithubCorner />
    </main>
  )
}
