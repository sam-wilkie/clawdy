/** Five steps from near white to Vinnie red. Cells snap to one of them, so the trail reads as pixels, not as a blur. */
export const PALETTE = ['#FDEBED', '#FAC9CE', '#F5A1AA', '#EC7480', '#DE4553'] as const

/**
 * Which palette step a lit cell takes: deeper near the pointer, paler at the edge of the reach, with a little
 * randomness so neighbours differ. away and reach are in cells; rnd returns a number in [0, 1].
 */
export function tintFor(away: number, reach: number, rnd: () => number): number {
  const near = Math.max(0, 1 - away / reach)
  return Math.max(0, Math.min(PALETTE.length - 1, Math.round(near * 3 + rnd())))
}

export interface PulseCell { col: number; row: number; away: number }

/**
 * The cells a pointer at (px, py) lights: the cell under it always, the rest of the disc of radius reach
 * with a chance that falls off with distance, so the edge of the trail breaks up instead of moving as a block.
 * Idea and falloff from the Grid Pulse component on 21st (carolinaraulino).
 */
export function pulseCells(px: number, py: number, cell: number, reach: number, rnd: () => number): PulseCell[] {
  const cx = Math.floor(px / cell), cy = Math.floor(py / cell)
  const span = Math.ceil(reach)
  const out: PulseCell[] = []
  for (let dy = -span; dy <= span; dy++) {
    for (let dx = -span; dx <= span; dx++) {
      const away = Math.hypot(dx, dy)
      if (away > reach) continue
      if (rnd() > 1 - away / (reach + 0.6)) continue
      out.push({ col: cx + dx, row: cy + dy, away })
    }
  }
  return out
}
