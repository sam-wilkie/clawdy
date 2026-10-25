/** Spin-to-dizzy: sums the signed angle of the pointer around Vinnie; two full turns one way, without long pauses, fire once. */
export function createSpin(o: { turns?: number; gapMs?: number; minR?: number; maxStep?: number } = {}) {
  const need = (o.turns ?? 2) * 2 * Math.PI
  const gap = o.gapMs ?? 400      // a longer pause resets the count
  const minR = o.minR ?? 30       // circle at a distance, do not jitter on the spot
  const maxStep = o.maxStep ?? 1.3 // rad per event; bigger jumps are teleports
  let last: number | null = null
  let sum = 0
  let lastT = 0

  const reset = () => { last = null; sum = 0 }

  function push(x: number, y: number, cx: number, cy: number, t: number): boolean {
    const dx = x - cx, dy = y - cy
    if (Math.hypot(dx, dy) < minR) { reset(); return false }
    const ang = Math.atan2(dy, dx)
    if (last !== null && t - lastT > gap) reset()
    if (last !== null) {
      let d = ang - last
      if (d > Math.PI) d -= 2 * Math.PI
      else if (d < -Math.PI) d += 2 * Math.PI
      if (Math.abs(d) > maxStep) sum = 0
      else if (d !== 0) {
        if (sum !== 0 && Math.sign(d) !== Math.sign(sum)) {
          if (Math.abs(d) > 0.03) sum = d // a real reversal restarts the turn; tiny jitter is ignored
        } else sum += d
      }
    }
    last = ang
    lastT = t
    if (Math.abs(sum) >= need) { reset(); return true }
    return false
  }

  return { push, reset }
}

/** Shake-to-dizzy while dragging, like the desktop pet: fast back-and-forth moves, 3 reversals within a second. */
export function createShake(o: { minSpeed?: number; reversals?: number; windowMs?: number } = {}) {
  const minSpeed = o.minSpeed ?? 6   // px per move to count as fast
  const need = o.reversals ?? 3      // direction flips needed
  const windowMs = o.windowMs ?? 1000 // the flips must fall inside this window
  let dir = 0
  let flips: number[] = []

  const reset = () => { dir = 0; flips = [] }

  /** dx: horizontal distance since the previous pointer move; t: timestamp in ms. True when it counts as a shake. */
  function push(dx: number, t: number): boolean {
    if (Math.abs(dx) < minSpeed) return false
    const d = dx > 0 ? 1 : -1
    let fired = false
    if (dir !== 0 && d !== dir) {
      flips = [...flips, t].filter((x) => t - x <= windowMs)
      if (flips.length >= need) { flips = []; fired = true }
    }
    dir = d
    return fired
  }

  return { push, reset }
}
