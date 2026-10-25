import type { RefObject } from 'react'
import { PROMPT, TOOL_COMMAND, stageIndex, type TerminalStage } from './terminal-script'

interface Props { stage: TerminalStage; text: string; dim: boolean; closing?: boolean; choice: 1 | 3; termRef: RefObject<HTMLDivElement | null> }

/** A macOS-style terminal window running a coding agent. The view only reads the stage the script has reached. */
export function Terminal({ stage, text, dim, closing, choice, termRef }: Props) {
  const at = (s: TerminalStage) => stageIndex(stage) >= stageIndex(s)
  const typing = stage === 'type'
  return (
    <div ref={termRef} className={`term${dim ? ' dim' : ''}${closing ? ' closing' : ''}`} role="img" aria-label="Terminal simulada de un agente de código">
      <div className="term-bar">
        <i className="dot r" /><i className="dot y" /><i className="dot g" />
        <span className="term-title">vinnie@clawdy: ~</span>
      </div>
      <div className="term-body">
        <div className="term-banner">
          <span className="term-glyph">&gt;_</span>
          <div><strong>Coding Agent</strong><br /><span className="muted">Opus 5.5 · esfuerzo alto</span><br /><span className="muted">~/clawdy</span></div>
        </div>

        <div className="term-log">
          {at('sent') && <p className="you"><span className="muted">&gt;</span> {PROMPT}</p>}
          {at('think') && <p className="think"><span className="spinner">✻</span> Pensando… <span className="muted">(esfuerzo alto)</span></p>}
          {at('tool') && (
            <div className="tool">
              <p><span className="bullet">●</span> <strong>Bash</strong><span className="muted">({TOOL_COMMAND})</span></p>
              <div className="tool-box">
                <p className="muted">Comando de Bash</p>
                <p>{TOOL_COMMAND}</p>
                <p className="muted">Clonar el repositorio de Clawdy</p>
                <p className="ask">¿Quieres continuar?</p>
                <p className={choice === 1 ? 'opt on' : 'opt'}>{choice === 1 ? '❯' : ' '} 1. Sí</p>
                <p className="opt">  2. Sí, y no preguntar otra vez por: git clone</p>
                <p className={choice === 3 ? 'opt on' : 'opt'}>{choice === 3 ? '❯' : ' '} 3. No</p>
                <p className="muted small">Esc para cancelar · Tab para editar · ctrl+e para explicar</p>
              </div>
            </div>
          )}
        </div>

        {!at('tool') && (
          <div className="term-input"><span className="muted">&gt;</span> {typing ? text : ''}<span className="caret">█</span></div>
        )}
        <div className="term-status">
          <span className="muted">{at('think') ? 'esc para interrumpir' : '? para atajos'}</span>
          <span className="effort">◎ alto · /effort</span>
        </div>
      </div>
    </div>
  )
}
