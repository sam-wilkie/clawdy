import { describe, expect, it } from 'vitest'
import { PALETTE, pulseCells, tintFor } from './pulse-field'

describe('PALETTE', () => {
  it('runs from near white to Vinnie red in five steps', () => {
    expect(PALETTE).toHaveLength(5)
    expect(PALETTE[0].toUpperCase()).toBe('#FDEBED')
    expect(PALETTE[4].toUpperCase()).toBe('#DE4553')
  })
})

describe('tintFor', () => {
  it('is the deepest red at the pointer and the palest at the edge of the reach', () => {
    expect(tintFor(0, 2.6, () => 1)).toBe(4)
    expect(tintFor(2.6, 2.6, () => 0)).toBe(0)
  })

  it('always stays inside the palette', () => {
    for (const away of [0, 1, 2, 2.6]) for (const r of [0, 0.5, 1]) {
      const i = tintFor(away, 2.6, () => r)
      expect(i).toBeGreaterThanOrEqual(0)
      expect(i).toBeLessThanOrEqual(PALETTE.length - 1)
    }
  })

  it('gets paler the further from the pointer, for the same dice roll', () => {
    expect(tintFor(0.5, 2.6, () => 0.5)).toBeGreaterThanOrEqual(tintFor(2.5, 2.6, () => 0.5))
  })
})

describe('pulseCells', () => {
  const cell = 37

  it('always lights the cell under the pointer, even when every roll says skip', () => {
    const cells = pulseCells(100, 200, cell, 2.6, () => 1)
    expect(cells.map((c) => [c.col, c.row])).toEqual([[2, 5]])
  })

  it('lights the whole disc around it when nothing is skipped', () => {
    const cells = pulseCells(100, 200, cell, 2.6, () => 0)
    expect(cells).toHaveLength(21) // a 5x5 block minus its four corners
    for (const c of cells) expect(c.away).toBeLessThanOrEqual(2.6)
  })

  it('never lights a cell beyond the reach', () => {
    const cells = pulseCells(100, 200, cell, 1.5, () => 0)
    for (const c of cells) expect(Math.hypot(c.col - 2, c.row - 5)).toBeLessThanOrEqual(1.5)
  })
})
