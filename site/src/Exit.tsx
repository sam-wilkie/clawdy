import { EXIT_LINE } from './showcase-data'
import { useTyped } from './useTyped'

const IRIS_MS = 900 // the dark iris closes in before the line starts typing

/** The farewell after a second Deny: dark screen, Vinnie in shades, a typed line, then a way back. */
export function Exit({ reduced, onRestart }: { reduced: boolean; onRestart: () => void }) {
  const { typed, done } = useTyped(EXIT_LINE, true, { delay: IRIS_MS + 400, ms: 100, instant: reduced })
  return (
    <div className="exit">
      <p className="exit-line" aria-live="polite">{typed}<span className="brand-cursor">▌</span></p>
      {done && <button type="button" className="exit-restart" onClick={onRestart} autoFocus>↻ Volver a empezar</button>}
    </div>
  )
}
