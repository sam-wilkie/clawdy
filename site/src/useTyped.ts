import { useEffect, useState } from 'react'

/** Types text out one character at a time once active (after delay ms). instant shows it whole, for reduced motion. */
export function useTyped(text: string, active: boolean, opts: { delay?: number; ms?: number; instant?: boolean } = {}) {
  const { delay = 0, ms = 100, instant = false } = opts
  const [n, setN] = useState(0)

  useEffect(() => {
    if (!active || instant) return
    let i = 0
    let id = window.setTimeout(function tick() {
      i++
      setN(i)
      if (i < text.length) id = window.setTimeout(tick, ms)
    }, delay)
    return () => { window.clearTimeout(id); setN(0) }
  }, [active, instant, text, delay, ms])

  const typed = !active ? '' : instant ? text : text.slice(0, n)
  return { typed, done: active && typed.length === text.length }
}
