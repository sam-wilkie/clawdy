import { useEffect, useRef } from 'react'
import { PALETTE, pulseCells, tintFor } from './pulse-field'

const CELL = 18       // half the page's dot grid (--grid is 36), so the pixels line up with the dots
const REACH = 3.4     // cells around the pointer that can catch light (about 60 px)
const MAX_LIT = 240   // a lid, so a fast sweep cannot light the whole page
const FADE_IN = 160   // ms
const FADE_OUT = 600  // ms

interface Cell { col: number; row: number; tint: number; born: number; until: number }

const easeOut = (t: number) => 1 - (1 - t) ** 2
const easeIn = (t: number) => t * t

/**
 * A red pixel trail that follows the pointer, always on: cells of the page's dot grid light up in five steps from
 * near white to Vinnie red and fade out a moment later. One canvas behind the page, asleep when nothing is lit.
 * Adapted from the Grid Pulse component on 21st (carolinaraulino), with a white-to-red ramp and no hairlines.
 */
export function PointerPulse({ reduced }: { reduced: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cv = canvas.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx || reduced) return
    const cells = new Map<string, Cell>()
    let cols = 1, rows = 1, width = 0, height = 0
    let frame = 0, pending = 0
    let at: { x: number; y: number } | null = null

    const draw = (now: number) => {
      frame = 0
      ctx.clearRect(0, 0, width, height)
      for (const [key, c] of cells) {
        let alpha: number
        if (now < c.until) alpha = easeOut(Math.min(1, (now - c.born) / FADE_IN))
        else {
          const t = (now - c.until) / FADE_OUT
          if (t >= 1) { cells.delete(key); continue }
          alpha = 1 - easeIn(t)
        }
        ctx.globalAlpha = alpha * 0.92
        ctx.fillStyle = PALETTE[c.tint]
        ctx.fillRect(c.col * CELL + 1, c.row * CELL + 1, CELL - 1, CELL - 1) // a 1 px gap keeps the cells apart
      }
      ctx.globalAlpha = 1
      if (cells.size > 0) frame = requestAnimationFrame(draw)
    }
    const wake = () => { if (!frame) frame = requestAnimationFrame(draw) }

    const size = () => {
      width = window.innerWidth
      height = window.innerHeight
      cols = Math.ceil(width / CELL)
      rows = Math.ceil(height / CELL)
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      cv.width = Math.round(width * dpr)
      cv.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      wake()
    }

    const paint = () => {
      pending = 0
      if (!at) return
      const now = performance.now()
      for (const c of pulseCells(at.x, at.y, CELL, REACH, Math.random)) {
        if (c.col < 0 || c.row < 0 || c.col >= cols || c.row >= rows) continue
        if (cells.size >= MAX_LIT) break
        const key = `${c.col},${c.row}`
        const lit = cells.get(key)
        if (lit && now < lit.until) continue
        // A cell caught again while it fades picks up from where it had got to instead of blinking out and in.
        let born = now
        if (lit) born = now - (1 - Math.sqrt(1 - (1 - easeIn(Math.min(1, (now - lit.until) / FADE_OUT))))) * FADE_IN
        cells.set(key, { col: c.col, row: c.row, tint: lit?.tint ?? tintFor(c.away, REACH, Math.random), born, until: now + 180 + Math.random() * 650 })
      }
      wake()
    }
    const onMove = (e: PointerEvent) => {
      at = { x: e.clientX, y: e.clientY }
      if (!pending) pending = requestAnimationFrame(paint)
    }

    size()
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('resize', size)
    return () => {
      cancelAnimationFrame(frame)
      cancelAnimationFrame(pending)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('resize', size)
    }
  }, [reduced])

  return <canvas ref={canvas} className="pulse" aria-hidden="true" />
}
