import { useEffect, useRef } from 'react'
import idleSvg from '../public/vinnie/idle.svg?raw'
import { approach, gazeTarget, settled, type Gaze } from './gaze'

const EYES_Y = 0.72 // the eyes sit about 72 % of the way down Vinnie's box

// The last pointer position, tracked even while the sprite is not mounted (Vinnie is an <img> in other states),
// so the face turns toward the pointer as soon as the idle sprite comes back.
let lastPointer: { x: number; y: number } | null = null
if (typeof window !== 'undefined') window.addEventListener('pointermove', (e) => { lastPointer = { x: e.clientX, y: e.clientY } }, { passive: true })

/**
 * Vinnie's idle animation as an inline SVG, so its face can follow the pointer: the whole face group slides over the
 * body (eased every frame, so it glides) while the idle beats keep playing. Only the idle state is inlined; every
 * other state is a plain <img>.
 */
export function GazeSprite({ follow }: { follow: boolean }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = host.current
    const face = root?.querySelector('.face-sq')
    if (!root || !face?.parentNode || !follow) return
    // Wrap the face once, so the idle keyframes on the face itself keep their own transform.
    const wrap = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    face.parentNode.insertBefore(wrap, face)
    wrap.appendChild(face)

    let cur: Gaze = { x: 0, y: 0 }
    let target: Gaze = { x: 0, y: 0 }
    let raf = 0
    const tick = () => {
      cur = approach(cur, target)
      if (settled(cur, target)) cur = target
      wrap.setAttribute('transform', `translate(${cur.x.toFixed(2)} ${cur.y.toFixed(2)})`)
      raf = settled(cur, target) ? 0 : requestAnimationFrame(tick)
    }
    const aim = (x: number | null, y: number | null) => {
      if (x === null || y === null) target = { x: 0, y: 0 }
      else {
        const r = root.getBoundingClientRect()
        target = gazeTarget(x - (r.left + r.width / 2), y - (r.top + r.height * EYES_Y))
      }
      if (!raf) raf = requestAnimationFrame(tick)
    }
    const onMove = (e: PointerEvent) => aim(e.clientX, e.clientY)
    const onLeave = () => aim(null, null)
    if (lastPointer) aim(lastPointer.x, lastPointer.y)
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('pointerdown', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerdown', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      wrap.parentNode?.insertBefore(face, wrap) // put the face back, so a re-run wraps it again cleanly
      wrap.remove()
    }
  }, [follow])

  return <div ref={host} className="gaze-sprite" aria-hidden="true" dangerouslySetInnerHTML={{ __html: idleSvg }} />
}
