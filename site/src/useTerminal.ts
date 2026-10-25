import { useEffect, useRef, useState } from 'react'
import type { Phase } from './flow'
import { PROMPT, T, type TerminalStage } from './terminal-script'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const CANCEL = Symbol('cancel')

/** Plays the terminal script while the flow is in the 'terminal' phase, then calls onReady (the permission card). */
export function useTerminal(phase: Phase, onReady: () => void): { stage: TerminalStage; text: string } {
  const [stage, setStage] = useState<TerminalStage>('type')
  const [text, setText] = useState('')
  const ready = useRef(onReady)
  useEffect(() => { ready.current = onReady })

  useEffect(() => {
    if (phase !== 'terminal') return
    let dead = false
    const alive = () => { if (dead) throw CANCEL }
    ;(async () => {
      try {
        await sleep(450); alive() // the window pops in first
        for (let i = 1; i <= PROMPT.length; i++) { setText(PROMPT.slice(0, i)); await sleep(T.typeChar); alive() }
        setStage('sent'); await sleep(T.sent); alive()
        setStage('think'); await sleep(T.think); alive()
        setStage('tool'); await sleep(T.tool); alive()
        ready.current()
      } catch (e) { if (e !== CANCEL) throw e }
    })()
    return () => { dead = true }
  }, [phase])

  // The permission phases keep the finished terminal on screen; a fresh run starts from the top.
  if (phase === 'permission' || phase === 'plead') return { stage: 'ready', text: PROMPT }
  if (phase !== 'terminal') return { stage: 'type', text: '' }
  return { stage, text }
}
