import { describe, expect, it } from 'vitest'
import { GAZE_MAX, approach, gazeTarget, settled } from './gaze'

describe('gazeTarget', () => {
  it('looks straight ahead when the pointer is on the eyes', () => {
    expect(gazeTarget(0, 0)).toEqual({ x: 0, y: 0 })
  })

  it('turns fully to a far pointer, never past the limit', () => {
    expect(gazeTarget(5000, 0)).toEqual({ x: GAZE_MAX.x, y: 0 })
    expect(gazeTarget(-5000, 0)).toEqual({ x: -GAZE_MAX.x, y: 0 })
    expect(gazeTarget(0, 5000).y).toBe(GAZE_MAX.y)
    expect(gazeTarget(0, -5000).y).toBe(-GAZE_MAX.y)
  })

  it('turns in proportion to how far the pointer is, up to the reach', () => {
    expect(gazeTarget(210, 0, 420).x).toBeCloseTo(GAZE_MAX.x / 2)
    expect(gazeTarget(0, -210, 420).y).toBeCloseTo(-GAZE_MAX.y / 2)
  })

  it('falls back to looking ahead on a non-finite input', () => {
    expect(gazeTarget(Number.NaN, 10)).toEqual({ x: 0, y: 0 })
    expect(gazeTarget(10, Number.POSITIVE_INFINITY)).toEqual({ x: 0, y: 0 })
  })
})

describe('approach', () => {
  it('moves a fraction of the way to the target', () => {
    const next = approach({ x: 0, y: 0 }, { x: 10, y: -4 }, 0.25)
    expect(next.x).toBeCloseTo(2.5)
    expect(next.y).toBeCloseTo(-1)
  })

  it('reaches the target at k = 1 and never overshoots', () => {
    expect(approach({ x: 3, y: 1 }, { x: -3, y: 0 }, 1)).toEqual({ x: -3, y: 0 })
    const a = approach({ x: 0, y: 0 }, { x: 1, y: 1 }, 0.9)
    expect(a.x).toBeLessThanOrEqual(1)
  })
})

describe('settled', () => {
  it('is true once the eyes are within a hair of the target', () => {
    expect(settled({ x: 2.995, y: 1 }, { x: 3, y: 1 })).toBe(true)
    expect(settled({ x: 2, y: 1 }, { x: 3, y: 1 })).toBe(false)
  })
})
