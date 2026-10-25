export interface Rect { left: number; top: number; right: number; bottom: number }
export interface Point { x: number; y: number }

export const contains = (r: Rect, x: number, y: number) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom

/** Vinnie's feet sit at the box centre, 89 % of the way down. */
export const feetOf = (r: Rect): Point => ({ x: (r.left + r.right) / 2, y: r.top + 0.89 * (r.bottom - r.top) })

/** Offset that moves Vinnie's feet to the centre of a zone, lifted above the zone's bottom edge. */
export const dockOffset = (feet: Point, zone: Rect, lift: number) => ({
  dx: (zone.left + zone.right) / 2 - feet.x,
  dy: zone.bottom - lift - feet.y,
})

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

/** Offset of Vinnie's feet while dragging: where it was left (base) plus the pointer delta, kept inside the viewport. */
export function dragOffset(feet: Point, base: { dx: number; dy: number }, delta: { dx: number; dy: number }, vw: number, vh: number, margin = 8, top = 80) {
  const fx = clamp(feet.x + base.dx + delta.dx, margin, vw - margin)
  const fy = clamp(feet.y + base.dy + delta.dy, top, vh - margin)
  return { dx: fx - feet.x, dy: fy - feet.y }
}

/** Vinnie's body centre sits this far above its feet; its feet rest this far above the bottom of the drop zone. */
export const BODY_LIFT = 40
export const DOCK_LIFT = 40
