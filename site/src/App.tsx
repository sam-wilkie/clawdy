import { useReducer, useRef, useState } from 'react'
import { ArcHint } from './ArcHint'
import { Exit } from './Exit'
import { Flowers } from './Flowers'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import { Intro } from './Intro'
import { PermCard } from './PermCard'
import { Pet } from './Pet'
import { phaseView } from './phase-view'
import { PointerPulse } from './PointerPulse'
import { Showcase } from './Showcase'
import { Terminal } from './Terminal'
import { useIntro } from './useIntro'
import { useStageActivity } from './useStageActivity'
import { useTerminal } from './useTerminal'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const skipIntro = new URLSearchParams(window.location.search).get('intro') === '0'

export default function App() {
  const [withIntro] = useState(() => wantsIntro({ reduced, skip: skipIntro }))
  const [flow, dispatch] = useReducer(reduce, withIntro, initialFlow)
  const intro = useIntro(flow.phase === 'intro', () => dispatch({ type: 'introDone' }))
  const term = useTerminal(flow.phase, () => dispatch({ type: 'terminalReady' }))
  const [restarts, setRestarts] = useState(0)
  const [entrance, setEntrance] = useState(!withIntro) // Vinnie walks in only when there is no intro
  const slotRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const zoneRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<HTMLDivElement>(null)

  const { phase } = flow
  const view = phaseView(phase)
  const act = useStageActivity(view.stage, reduced)

  const restart = () => {
    const playIntro = wantsIntro({ reduced, skip: skipIntro })
    dispatch({ type: 'restart', intro: playIntro }) // back to the start screen
    setEntrance(!playIntro)
    setRestarts((n) => n + 1) // a fresh Vinnie
    act.reset()
  }

  return (
    <main className="stage" data-phase={phase} data-frame={view.intro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <PointerPulse reduced={reduced} />
      <Flowers show={(act.bloomed || act.drag.dragging) && (view.stage || view.terminal)} bodyRef={bodyRef} follow={view.spot !== 'terminal'} reduced={reduced} />
      {view.intro && <Intro {...intro} />}
      {view.exit && <Exit reduced={reduced} onRestart={restart} />}
      <div ref={zoneRef} className={`drop-zone${act.drag.dragging || view.stage ? ' show' : ''}${act.drag.over ? ' over' : ''}`} aria-hidden="true">Suéltame aquí</div>
      <ArcHint show={view.stage && act.arcReady && !act.dragged && !act.bloomed} petRef={slotRef} zoneRef={zoneRef} />
      {view.terminal && <Terminal stage={term.stage} text={term.text} dim={view.asking} choice={phase === 'plead' ? 3 : 1} termRef={termRef} />}
      {view.asking && <PermCard pleading={phase === 'plead'} onAllow={() => dispatch({ type: 'allow' })} onDeny={() => dispatch({ type: 'deny' })} />}
      {view.showcase && <Showcase onRestart={restart} />}
      {!view.petHidden && (
        <Pet
          key={restarts}
          phase={phase}
          spot={view.spot}
          slotRef={slotRef}
          bodyRef={bodyRef}
          zoneRef={zoneRef}
          termRef={termRef}
          forced={view.intro && intro.frame === '3' ? 'alert' : view.mood}
          entrance={entrance}
          reduced={reduced}
          onDrag={act.onDrag}
          onPoke={act.poke}
          onDrop={() => dispatch({ type: 'dropped' })}
        />
      )}
      {view.stage && !act.bloomed && !act.drag.dragging && <p className="hint" aria-hidden="true">Prueba a arrastrarme</p>}
      <GithubCorner hidden={view.showcase} />
    </main>
  )
}
