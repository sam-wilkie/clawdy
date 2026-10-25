import { useEffect, useRef } from 'react'
import { TOOL_COMMAND } from './terminal-script'

/** The permission card. After the first Deny it shows Vinnie's plea; the second Deny ends the visit. */
export function PermCard({ pleading, leaving, onAllow, onDeny }: { pleading: boolean; leaving: boolean; onAllow: () => void; onDeny: () => void }) {
  const allow = useRef<HTMLButtonElement>(null)
  useEffect(() => { allow.current?.focus({ preventScroll: true }) }, [])
  return (
    <dialog open className={`perm${pleading ? ' pleading' : ''}${leaving ? ' leaving' : ''}`} aria-label="Solicitud de permiso">
      <div className="perm-head">
        <h2>Solicitud de permiso</h2>
        <span className="pill">BASH</span>
      </div>
      <code className="perm-code">{TOOL_COMMAND}</code>
      {pleading && <p className="perm-plea">Puedo empezar solo con el repo… lo prometo.</p>}
      <div className="perm-actions">
        <button ref={allow} type="button" className="btn allow" disabled={leaving} onClick={onAllow}>Permitir</button>
        <button type="button" className="btn deny" disabled={leaving} onClick={onDeny}>Rechazar</button>
      </div>
    </dialog>
  )
}
