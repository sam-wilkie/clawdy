import type { Point } from './geometry'

export interface Flower {
  x: number; y: number; alpha: number; scale: number
  motif: readonly string[]; color: string; core: string
  delay: number; phase: number; speed: number
}

export const PX = 2                // one flower pixel, CSS px
export const STAGGER = 5           // ms of delay per px from the patch centre
const COLORS = ['#DE4553', '#0A0A0A', '#DE4553', '#0A0A0A']   // brand: Vinnie red, ink
const CORES = ['#FFFFFF', '#FAFAFA', '#FFFFFF', '#FAFAFA']
// 7x7 motifs: X = petal, o = core.
export const MOTIFS = [
  ['..XXX..', '..XXX..', 'XXXXXXX', 'XXXoXXX', 'XXXXXXX', '..XXX..', '..XXX..'], // plus
  ['..XXX..', '.XXXXX.', 'XXXXXXX', 'XXXoXXX', 'XXXXXXX', '.XXXXX.', '..XXX..'], // round
  ['.......', '...X...', '..XXX..', '.XXoXX.', '..XXX..', '...X...', '.......'], // bud
] as const

function hash(x: number, y: number): number {
  let h = (x * 374761393 + y * 668265263) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return (h ^ (h >>> 16)) >>> 0
}

/** A round patch of pixel flowers sitting on the centres of the page's dot grid (cell = grid px). */
export function buildFlowers(center: Point, radius: number, grid: number): Flower[] {
  const out: Flower[] = []
  const gx0 = Math.floor((center.x - radius) / grid), gx1 = Math.ceil((center.x + radius) / grid)
  const gy0 = Math.floor((center.y - radius) / grid), gy1 = Math.ceil((center.y + radius) / grid)
  for (let gy = gy0; gy <= gy1; gy++) {
    for (let gx = gx0; gx <= gx1; gx++) {
      const cx = gx * grid + grid / 2, cy = gy * grid + grid / 2
      const dist = Math.hypot(cx - center.x, cy - center.y)
      if (dist >= radius) continue
      const h = hash(gx, gy)
      if (h % 7 === 0 && dist > radius * 0.45) continue // a few gaps near the rim
      const strength = Math.pow(1 - dist / radius, 0.7)
      out.push({
        x: cx, y: cy,
        alpha: 0.18 + strength * 0.72,
        scale: 0.7 + strength * 0.4,
        motif: MOTIFS[dist > radius * 0.75 ? 2 : (h >>> 3) % 2],
        color: COLORS[(h >>> 5) % COLORS.length],
        core: CORES[(h >>> 5) % CORES.length],
        delay: dist * STAGGER,
        phase: (h % 628) / 100,
        speed: 0.6 + (h % 50) / 100,
      })
    }
  }
  return out
}
