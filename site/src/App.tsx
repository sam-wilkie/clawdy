import { useEffect, useReducer, useRef, useState } from 'react'
import { ArcHint } from './ArcHint'
import { Flowers } from './Flowers'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import { markSeen, readSeen } from './intro-schedule'
import { Intro } from './Intro'
import { PermCard } from './PermCard'
import { Pet, type DragInfo, type Spot } from './Pet'
import { PixelHearts } from './PixelHearts'
import { Terminal } from './Terminal'
import { useIntro } from './useIntro'
import { useTerminal } from './useTerminal'
import type { VinnieState } from './vinnie-states'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const forced = new URLSearchParams(window.location.search).get('intro') === '1'
const ARC_DELAY = 3000 // ms on the stage before the dashed arc shows the way

export default function App() {
  const [withIntro] = useState(() => wantsIntro({ reduced, forced, seen: readSeen() }))
  const [flow, dispatch] = useReducer(reduce, withIntro, initialFlow)
  const intro = useIntro(flow.phase === 'intro', () => { markSeen(); dispatch({ type: 'introDone' }) })
  const term = useTerminal(flow.phase, () => dispatch({ type: 'terminalReady' }))
  const [drag, setDrag] = useState<DragInfo>({ dragging: false, over: false })
  const [dragged, setDragged] = useState(false)
  const [arcReady, setArcReady] = useState(false)
  const slotRef = useRef<HTMLDivElement>(null)
  const zoneRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<HTMLDivElement>(null)

  const { phase } = flow
  const inIntro = phase === 'intro'
  const stage = phase === 'stage'
  const asking = phase === 'permission' || phase === 'plead'
  const inTerminal = phase === 'terminal' || asking

  useEffect(() => {
    if (!stage || dragged || reduced) return
    const id = window.setTimeout(() => setArcReady(true), ARC_DELAY)
    return () => window.clearTimeout(id)
  }, [stage, dragged])

  const spot: Spot = phase === 'terminal' ? 'zone' : asking ? 'terminal' : 'rest'
  const mood: VinnieState | undefined =
    inIntro && intro.frame === '3' ? 'alert' : phase === 'permission' ? 'alert' : phase === 'plead' ? 'happy' : undefined

  return (
    <main className="stage" data-phase={phase} data-frame={inIntro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <Flowers show={drag.dragging || inTerminal} zoneRef={zoneRef} reduced={reduced} />
      {inIntro && <Intro {...intro} />}
      <div ref={zoneRef} className={`drop-zone${drag.dragging ? ' show' : ''}${drag.over ? ' over' : ''}`} aria-hidden="true">Suéltame aquí</div>
      <ArcHint show={stage && arcReady && !dragged} petRef={slotRef} zoneRef={zoneRef} />
      {inTerminal && <Terminal stage={term.stage} text={term.text} dim={asking} choice={phase === 'plead' ? 3 : 1} termRef={termRef} />}
      {asking && <PermCard pleading={phase === 'plead'} onAllow={() => dispatch({ type: 'allow' })} onDeny={() => dispatch({ type: 'deny' })} />}
      <Pet
        phase={phase}
        spot={spot}
        slotRef={slotRef}
        zoneRef={zoneRef}
        termRef={termRef}
        forced={mood}
        extra={phase === 'plead' ? <PixelHearts /> : undefined}
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
