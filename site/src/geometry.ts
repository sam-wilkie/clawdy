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
