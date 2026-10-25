import { useCallback, useEffect, useRef, useState } from 'react'
import { T, TITLE, type IntroFrame } from './intro-schedule'

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const CANCEL = Symbol('cancel')

/** Runs the intro (cursor, typing, flash, delete, centre, iris). skip() ends it at once; onDone fires once either way. */
export function useIntro(active: boolean, onDone: () => void) {
  const [frame, setFrame] = useState<IntroFrame>('1a')
  const [text, setText] = useState('')
  const [lit, setLit] = useState(true)
  const done = useRef(onDone)
  const stop = useRef<() => void>(() => {})
  useEffect(() => { done.current = onDone })

  useEffect(() => {
    if (!active) return
    let dead = false
    const alive = () => { if (dead) throw CANCEL }
    stop.current = () => { if (!dead) { dead = true; done.current() } }
    ;(async () => {
      try {
        setFrame('1a'); setText(''); setLit(true)
        await sleep(T.cursorOnly); alive()
        setFrame('1b')
        for (let i = 1; i <= TITLE.length; i++) { setText(TITLE.slice(0, i)); await sleep(T.typeForward); alive() }
        setFrame('1c')
        for (let n = 0; n < T.flashCount; n++) {
          setLit(false); await sleep(T.flashDur / 2); alive()
          setLit(true); await sleep(T.flashDur / 2); alive()
        }
        setFrame('1d')
        for (let i = TITLE.length - 1; i >= 0; i--) { setText(TITLE.slice(0, i)); await sleep(T.typeReverse); alive() }
        await sleep(T.afterDelete); alive()
        setFrame('1e'); await sleep(T.centerMove); alive()
        setFrame('3'); await sleep(T.react); alive()
        dead = true
        done.current()
      } catch (e) { if (e !== CANCEL) throw e }
    })()
    return () => { dead = true; setFrame('1a'); setText(''); setLit(true) }
  }, [active])

  const skip = useCallback(() => stop.current(), [])
  return { frame, text, lit, skip }
}
