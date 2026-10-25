import { useEffect, useRef, type RefObject } from 'react'
import { PX, buildFlowers, type Flower } from './flower-field'
import { BODY_LIFT, feetOf, type Point } from './geometry'

const GRID = 36  // keep in sync with --grid in index.css
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

interface Props {
  show: boolean
  bodyRef: RefObject<HTMLElement | null> // Vinnie's moving box: the patch is centred on its body, read every frame
  follow: boolean                        // false keeps the patch where it was (Vinnie waits beside the terminal)
  reduced: boolean
}

/** A patch of pixel flowers around Vinnie. Blooms fade in from the centre, then breathe softly; the patch follows Vinnie. */
export function Flowers({ show, bodyRef, follow, reduced }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const following = useRef(follow)
  useEffect(() => { following.current = follow })

  useEffect(() => {
    const cv = canvas.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx) return
    let raf = 0
    let flowers: Flower[] = []
    let built: Point | null = null
    let at: Point | null = null
    let started = 0
    let last = 0
    let dpr = 1

    const clear = () => { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height) }
    const rebuild = () => {
      const r = bodyRef.current?.getBoundingClientRect()
      if (following.current && r && r.width > 0) { const f = feetOf(r); at = { x: f.x, y: f.y - BODY_LIFT } }
      if (!at) { flowers = []; built = null; return }
      if (built && Math.abs(built.x - at.x) < 0.5 && Math.abs(built.y - at.y) < 0.5) return
      built = at
      flowers = buildFlowers(at, window.innerWidth <= 600 ? 84 : 104, GRID)
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
    const repaint = () => { size(); paint(performance.now()) }
    const settle = () => paint(performance.now()) // reduced motion has no loop: repaint once a drag ends

    if (!show) { clear(); return }
    size()
    started = performance.now()
    if (reduced) paint(started)
    else raf = requestAnimationFrame(loop)
    window.addEventListener('resize', repaint)
    window.addEventListener('pointerup', settle)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      if (raf) cancelAnimationFrame(raf)
      window.removeEventListener('resize', repaint)
      window.removeEventListener('pointerup', settle)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [show, bodyRef, reduced])

  return <canvas ref={canvas} className="flowers" aria-hidden="true" />
}
