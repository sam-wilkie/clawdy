import { useEffect, useReducer, useRef, useState } from 'react'
import { ArcHint } from './ArcHint'
import { Exit } from './Exit'
import { Flowers } from './Flowers'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import type { Point } from './geometry'
import { Intro } from './Intro'
import { PermCard } from './PermCard'
import { Pet, type DragInfo } from './Pet'
import { phaseView } from './phase-view'
import { Showcase } from './Showcase'
import { Terminal } from './Terminal'
import { useIntro } from './useIntro'
import { useTerminal } from './useTerminal'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const skipIntro = new URLSearchParams(window.location.search).get('intro') === '0'
const ARC_DELAY = 3000 // ms on the stage before the dashed arc shows the way
const NO_DRAG: DragInfo = { dragging: false, over: false }

export default function App() {
  const [withIntro] = useState(() => wantsIntro({ reduced, skip: skipIntro }))
  const [flow, dispatch] = useReducer(reduce, withIntro, initialFlow)
  const intro = useIntro(flow.phase === 'intro', () => dispatch({ type: 'introDone' }))
  const term = useTerminal(flow.phase, () => dispatch({ type: 'terminalReady' }))
  const [drag, setDrag] = useState<DragInfo>(NO_DRAG)
  const [dragged, setDragged] = useState(false)
  const [arcReady, setArcReady] = useState(false)
  const [bloomed, setBloomed] = useState(false) // the first click or drag makes the flowers bloom
  const [petCenter, setPetCenter] = useState<Point | null>(null)
  const [restarts, setRestarts] = useState(0)
  const [entrance, setEntrance] = useState(!withIntro) // Vinnie walks in only when there is no intro
  const slotRef = useRef<HTMLDivElement>(null)
  const zoneRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<HTMLDivElement>(null)

  const { phase } = flow
  const view = phaseView(phase)

  useEffect(() => {
    if (!view.stage || dragged || reduced) return
    const id = window.setTimeout(() => setArcReady(true), ARC_DELAY)
    return () => window.clearTimeout(id)
  }, [view.stage, dragged])

  const restart = () => {
    const intro = wantsIntro({ reduced, skip: skipIntro })
    dispatch({ type: 'restart', intro }) // back to the start screen
    setEntrance(!intro)
    setRestarts((n) => n + 1) // a fresh Vinnie
    setDragged(false)
    setBloomed(false)
    setPetCenter(null)
    setArcReady(false)
    setDrag(NO_DRAG)
  }

  return (
    <main className="stage" data-phase={phase} data-frame={view.intro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <Flowers show={(bloomed || drag.dragging) && (view.stage || view.terminal)} center={petCenter} reduced={reduced} />
      {view.intro && <Intro {...intro} />}
      {view.exit && <Exit reduced={reduced} onRestart={restart} />}
      <div ref={zoneRef} className={`drop-zone${drag.dragging || (dragged && view.stage) ? ' show' : ''}${drag.over ? ' over' : ''}`} aria-hidden="true">Suéltame aquí</div>
      <ArcHint show={view.stage && arcReady && !dragged && !bloomed} petRef={slotRef} zoneRef={zoneRef} />
      {view.terminal && <Terminal stage={term.stage} text={term.text} dim={view.asking} choice={phase === 'plead' ? 3 : 1} termRef={termRef} />}
      {view.asking && <PermCard pleading={phase === 'plead'} onAllow={() => dispatch({ type: 'allow' })} onDeny={() => dispatch({ type: 'deny' })} />}
      {view.showcase && <Showcase onRestart={restart} />}
      {!view.petHidden && (
        <Pet
          key={restarts}
          phase={phase}
          spot={view.spot}
          slotRef={slotRef}
          zoneRef={zoneRef}
          termRef={termRef}
          forced={view.intro && intro.frame === '3' ? 'alert' : view.mood}
          entrance={entrance}
          reduced={reduced}
          onDrag={(d) => { setDrag(d); if (d.dragging) { setDragged(true); setBloomed(true) } }}
          onPoke={() => setBloomed(true)}
          onCenter={setPetCenter}
          onDrop={() => dispatch({ type: 'dropped' })}
        />
      )}
      {view.stage && !bloomed && !drag.dragging && <p className="hint" aria-hidden="true">Prueba a arrastrarme</p>}
      <GithubCorner hidden={view.showcase} />
    </main>
  )
}
