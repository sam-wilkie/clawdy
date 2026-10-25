export interface Gaze { x: number; y: number }

/** How far the face slides over the body, in art pixels (1 art pixel = half a viewBox unit). */
/** (5, 3) is about as far as the face can slide before it leaves the body's edge. */
export const GAZE_MAX: Gaze = { x: 5, y: 3 }

/** Distance from the eyes (CSS px) at which the face has turned fully; vertical is shorter, the page is wider than tall. */
export const REACH: Gaze = { x: 170, y: 110 }

const clamp = (v: number, lim: number) => Math.max(-lim, Math.min(lim, v))

/** Where the face should be for a pointer at (dx, dy) CSS px from the eyes; it turns fully at REACH px or more. */
export function gazeTarget(dx: number, dy: number): Gaze {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return { x: 0, y: 0 }
  return {
    x: clamp(dx / REACH.x, 1) * GAZE_MAX.x,
    y: clamp(dy / REACH.y, 1) * GAZE_MAX.y,
  }
}

/** One easing step toward the target (k = 1 jumps there); called every frame it gives a smooth glide. */
export function approach(cur: Gaze, target: Gaze, k = 0.16): Gaze {
  return { x: cur.x + (target.x - cur.x) * k, y: cur.y + (target.y - cur.y) * k }
}

export const settled = (cur: Gaze, target: Gaze, eps = 0.01) =>
  Math.abs(cur.x - target.x) < eps && Math.abs(cur.y - target.y) < eps
