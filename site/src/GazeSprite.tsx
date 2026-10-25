import { useEffect, useRef } from 'react'
import idleSvg from '../public/vinnie/idle.svg?raw'
import { approach, bodyLean, gazeTarget, settled, shadowOf, type Gaze, type Look } from './gaze'

const EYES_Y = 0.72 // the eyes sit about 72 % of the way down Vinnie's box
const AHEAD: Gaze = { x: 0, y: 0 }
const SVG_NS = 'http://www.w3.org/2000/svg'

// The last pointer position, tracked even while the sprite is not mounted (Vinnie is an <img> in other states),
// so the face turns toward the pointer as soon as the idle sprite comes back.
let lastPointer: { x: number; y: number } | null = null
if (typeof window !== 'undefined') window.addEventListener('pointermove', (e) => { lastPointer = { x: e.clientX, y: e.clientY } }, { passive: true })

/** Wrap sibling nodes in one <g>, so the idle keyframes on the nodes themselves keep their own transform. */
function wrap(...nodes: Element[]) {
  const g = document.createElementNS(SVG_NS, 'g')
  nodes[0].parentNode?.insertBefore(g, nodes[0])
  for (const n of nodes) g.appendChild(n)
  return g
}

function unwrap(g: SVGGElement) {
  while (g.firstChild) g.parentNode?.insertBefore(g.firstChild, g)
  g.remove()
}

/**
 * Vinnie's idle animation as an inline SVG, so he can look around: the face slides over the body and the body leans a
 * third as far (the shadow with it), all eased every frame so it glides while the idle beats keep playing. `look`
 * says what he looks at: the pointer (null), straight ahead, or the intro's typing cursor, which he reads as it
 * moves. Only the idle state is inlined; every other state is a plain <img>.
 */
export function GazeSprite({ follow, look = null }: { follow: boolean; look?: Look }) {
  const host = useRef<HTMLDivElement>(null)
  const lookRef = useRef(look)
  const aimRef = useRef<() => void>(() => {})

  useEffect(() => {
    lookRef.current = look
    aimRef.current() // a new thing to look at: start gliding to it now
  }, [look])

  useEffect(() => {
    const root = host.current
    const face = root?.querySelector('.face-sq'), bob = root?.querySelector('.bob'), shadows = root?.querySelectorAll('.sh-n, .sh-s')
    if (!root || !face || !bob || !shadows?.length || !follow) return
    const faceG = wrap(face), bodyG = wrap(bob), shadowG = wrap(...shadows)
    shadowG.style.transformBox = 'view-box'
    shadowG.style.transformOrigin = '15px 30px' // the feet, in the scaled art space

    let cur: Gaze = AHEAD
    let target: Gaze = AHEAD
    let raf = 0
    const reading = () => lookRef.current === 'cursor' // the cursor moves: keep re-aiming every frame
    const resolve = (): Gaze => {
      const look = lookRef.current
      if (look === 'center') return AHEAD
      const at = look === 'cursor' ? document.querySelector('.brand-cursor')?.getBoundingClientRect() : undefined
      const point = at ? { x: at.left + at.width / 2, y: at.top + at.height / 2 } : look === 'cursor' ? null : lastPointer
      if (!point) return AHEAD
      const r = root.getBoundingClientRect()
      return gazeTarget(point.x - (r.left + r.width / 2), point.y - (r.top + r.height * EYES_Y))
    }
    const tick = () => {
      if (reading()) target = resolve()
      cur = approach(cur, target)
      if (settled(cur, target)) cur = target
      const lean = bodyLean(cur), shadow = shadowOf(lean)
      faceG.setAttribute('transform', `translate(${cur.x.toFixed(2)} ${cur.y.toFixed(2)})`)
      bodyG.setAttribute('transform', `translate(${lean.x} ${lean.y})`)
      shadowG.style.transform = `translateX(${shadow.shift}px) scaleX(${shadow.stretch})`
      raf = settled(cur, target) && !reading() ? 0 : requestAnimationFrame(tick)
    }
    const aim = () => {
      target = resolve()
      if (!raf) raf = requestAnimationFrame(tick)
    }
    aimRef.current = aim
    const onMove = () => { if (lookRef.current === null) aim() }
    const onLeave = () => { lastPointer = null; if (lookRef.current === null) aim() }
    aim()
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('pointerdown', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)
    return () => {
      cancelAnimationFrame(raf)
      aimRef.current = () => {}
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerdown', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      unwrap(shadowG); unwrap(bodyG); unwrap(faceG) // put the sprite back, so a re-run wraps it again cleanly
    }
  }, [follow])

  return <div ref={host} className="gaze-sprite" aria-hidden="true" dangerouslySetInnerHTML={{ __html: idleSvg }} />
}
