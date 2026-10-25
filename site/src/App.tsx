import { useReducer } from 'react'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce, wantsIntro } from './flow'
import { markSeen, readSeen } from './intro-schedule'
import { Intro } from './Intro'
import { useIntro } from './useIntro'
import { Vinnie } from './Vinnie'
import './App.css'

const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const forced = new URLSearchParams(window.location.search).get('intro') === '1'

export default function App() {
  const [flow, dispatch] = useReducer(reduce, undefined, () => initialFlow(wantsIntro({ reduced, forced, seen: readSeen() })))
  const intro = useIntro(flow.phase === 'intro', () => { markSeen(); dispatch({ type: 'introDone' }) })
  const inIntro = flow.phase === 'intro'

  return (
    <main className="stage" data-phase={flow.phase} data-frame={inIntro ? intro.frame : '4'}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      {inIntro && <Intro {...intro} />}
      <div className="pet">
        <Vinnie state={inIntro && intro.frame === '3' ? 'alert' : 'idle'} />
      </div>
      {flow.phase === 'stage' && <p className="hint" aria-hidden="true">Prueba a arrastrarme</p>}
      <div className="drop-zone" aria-hidden="true">Suéltame aquí</div>
      <GithubCorner />
    </main>
  )
}
