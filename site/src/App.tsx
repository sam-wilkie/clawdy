import { useReducer, useRef, useState } from 'react'
import { ArcHint } from './ArcHint'
import { Exit } from './Exit'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import { lookTarget } from './gaze'
import { Intro } from './Intro'
import { PermCard } from './PermCard'
import { Pet } from './Pet'
import { phaseView } from './phase-view'
import { PointerPulse } from './PointerPulse'
import { Showcase } from './Showcase'
import { Terminal } from './Terminal'
import { useAllow } from './useAllow'
import { useIntro } from './useIntro'
import { useMood } from './useMood'
import { useStageActivity } from './useStageActivity'
import { useTerminal } from './useTerminal'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const skipIntro = new URLSearchParams(window.location.search).get('intro') === '0'
const NARROW = 760 // below this width the terminal fills the screen: no window edge to slip behind

export default function App() {
  const [withIntro] = useState(() => wantsIntro({ reduced, skip: skipIntro }))
  const [flow, dispatch] = useReducer(reduce, withIntro, initialFlow)
  const intro = useIntro(flow.phase === 'intro', () => dispatch({ type: 'introDone' }))
  const term = useTerminal(flow.phase, () => dispatch({ type: 'terminalReady' }))
  const [restarts, setRestarts] = useState(0)
  const [entrance, setEntrance] = useState(!withIntro) // Vinnie walks in only when there is no intro
  const slotRef = useRef<HTMLDivElement>(null)
  const zoneRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<HTMLDivElement>(null)

  const { phase } = flow
  const compact = reduced || window.innerWidth < NARROW
  const view = phaseView(phase, term.stage, compact)
  const act = useStageActivity(view.stage, reduced)
  const mood = useMood(phase, term.stage, compact)
  const closing = useAllow(phase, reduced, () => dispatch({ type: 'allowed' })) // the terminal shrinks away after Allow

  const restart = () => {
    const playIntro = wantsIntro({ reduced, skip: skipIntro })
    dispatch({ type: 'restart', intro: playIntro }) // back to the start screen
    setEntrance(!playIntro)
    setRestarts((n) => n + 1) // a fresh Vinnie
    act.reset()
  }

  return (
    <main className="stage" data-phase={phase} data-dragging={act.drag.dragging || undefined} data-frame={view.intro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <PointerPulse reduced={reduced} />
      {view.intro && <Intro {...intro} />}
      {view.exit && <Exit reduced={reduced} onRestart={restart} />}
      <div ref={zoneRef} className={`drop-zone${act.drag.dragging || view.stage ? ' show' : ''}${act.drag.over ? ' over' : ''}`} aria-hidden="true">Suéltame aquí</div>
      <ArcHint show={view.stage && act.arcReady && !act.dragged && !act.poked} petRef={slotRef} zoneRef={zoneRef} />
      {view.terminal && <Terminal stage={term.stage} text={term.text} dim={view.asking || view.allowing} closing={closing} choice={phase === 'plead' ? 3 : 1} termRef={termRef} />}
      {(view.asking || view.allowing) && <PermCard pleading={phase === 'plead' || (view.allowing && flow.denies > 0)} leaving={view.allowing} onAllow={() => dispatch({ type: 'allow' })} onDeny={() => dispatch({ type: 'deny' })} />}
      {view.showcase && <Showcase onRestart={restart} />}
      {!view.petHidden && (
        <Pet
          key={restarts}
          phase={phase}
          spot={view.spot}
          behind={view.behind}
          slotRef={slotRef}
          zoneRef={zoneRef}
          termRef={termRef}
          forced={view.intro && intro.frame === '3' ? 'panic' : view.mood ?? mood}
          look={view.allowing ? 'center' : lookTarget(view.intro ? intro.frame : undefined)}
          leaving={closing}
          entrance={entrance}
          reduced={reduced}
          onDrag={act.onDrag}
          onPoke={act.poke}
          onDrop={() => dispatch({ type: 'dropped' })}
        />
      )}
      {view.stage && !act.poked && !act.drag.dragging && <p className="hint" aria-hidden="true">Prueba a arrastrarme</p>}
      <GithubCorner hidden={view.showcase} />
    </main>
  )
}
