import { useReducer } from 'react'
import { GithubCorner } from './GithubCorner'
import { initialFlow, reduce } from './flow'
import { Vinnie } from './Vinnie'
import './App.css'

export default function App() {
  const [flow] = useReducer(reduce, false, initialFlow)
  return (
    <main className="stage" data-phase={flow.phase}>
      <h1 className="sr">Clawdy, una mascota pixel art llamada Vinnie que reacciona a tus sesiones de Claude Code.</h1>
      <div className="vinnie-box">
        <Vinnie state="idle" />
      </div>
      <GithubCorner />
    </main>
  )
}
