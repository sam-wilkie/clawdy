import { useEffect, useRef } from 'react'
import { PX, buildFlowers, type Flower } from './flower-field'
import type { Point } from './geometry'

const GRID = 37  // keep in sync with --grid in index.css
const FADE = 700 // ms per bloom
const FPS = 12   // breathing is slow, no need for 60 fps

function draw(ctx: CanvasRenderingContext2D, f: Flower, alpha: number) {
  if (alpha <= 0.01) return
  const size = PX * f.scale, half = size * 3.5
  ctx.globalAlpha = alpha
  f.motif.forEach((row, r) => {
    for (let c = 0; c < 7; c++) {
      const ch = row[c]
      if (ch === '.') continue
      ctx.fillStyle = ch === 'o' ? f.core : f.color
      ctx.fillRect(f.x - half + c * size, f.y - half + r * size, size, size)
    }
  })
}

/** A patch of pixel flowers around Vinnie. Blooms fade in from the centre, then breathe softly; the patch follows Vinnie. */
export function Flowers({ show, center, reduced }: { show: boolean; center: Point | null; reduced: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const at = useRef<Point | null>(center)
  const refresh = useRef<() => void>(() => {})

  // The loop below reads the centre through a ref, so moving Vinnie never restarts the bloom.
  useEffect(() => { at.current = center; refresh.current() }, [center])

  useEffect(() => {
    const cv = canvas.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx) return
    let raf = 0
    let flowers: Flower[] = []
    let built: Point | null = null
    let started = 0
    let last = 0
    let dpr = 1

    const clear = () => { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height) }
    const rebuild = () => {
      const c = at.current
      if (!c) { flowers = []; built = null; return }
      if (built && built.x === c.x && built.y === c.y) return
      built = c
      flowers = buildFlowers(c, window.innerWidth <= 600 ? 84 : 104, GRID)
    }
    const paint = (now: number) => {
      rebuild()
      clear()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const t = now - started
      for (const f of flowers) {
        let k = 1
        if (!reduced) {
          k = Math.max(0, Math.min(1, (t - f.delay) / FADE))
          k *= 0.88 + 0.12 * Math.sin(now / 1000 * f.speed + f.phase) // soft breathing
        }
        draw(ctx, f, f.alpha * k)
      }
      ctx.globalAlpha = 1
    }
    const size = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1)
      cv.width = Math.round(window.innerWidth * dpr)
      cv.height = Math.round(window.innerHeight * dpr)
      built = null
    }
    const loop = (now: number) => {
      raf = 0
      if (document.hidden) return
      if (now - last >= 1000 / FPS) { last = now; paint(now) }
      raf = requestAnimationFrame(loop)
    }
    const onVisible = () => { if (!document.hidden && !reduced && !raf) raf = requestAnimationFrame(loop) }
    const onResize = () => { size(); paint(performance.now()) }

    if (!show) { clear(); refresh.current = () => {}; return }
    size()
    started = performance.now()
    refresh.current = () => { if (reduced) paint(performance.now()) } // animated mode repaints on its own
    if (reduced) paint(started)
    else raf = requestAnimationFrame(loop)
    window.addEventListener('resize', onResize)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      if (raf) cancelAnimationFrame(raf)
      refresh.current = () => {}
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [show, reduced])

  return <canvas ref={canvas} className="flowers" aria-hidden="true" />
}
