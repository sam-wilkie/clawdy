import { describe, expect, it } from 'vitest'
import { GAZE_MAX, REACH, approach, bodyLean, gazeTarget, lookTarget, settled, shadowOf } from './gaze'

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
    expect(gazeTarget(REACH.x / 2, 0).x).toBeCloseTo(GAZE_MAX.x / 2)
    expect(gazeTarget(0, -REACH.y / 2).y).toBeCloseTo(-GAZE_MAX.y / 2)
  })

  it('turns fully to a pointer that is only a hand away, not across the screen', () => {
    expect(REACH.x).toBeLessThanOrEqual(200)
    expect(REACH.y).toBeLessThanOrEqual(REACH.x)
    expect(gazeTarget(REACH.x, 0).x).toBe(GAZE_MAX.x)
    expect(gazeTarget(0, REACH.y).y).toBe(GAZE_MAX.y)
  })

  it('moves the face enough up and down to be seen, not just a pixel', () => {
    expect(GAZE_MAX.y).toBeGreaterThanOrEqual(3)
    expect(GAZE_MAX.x).toBeGreaterThanOrEqual(5)
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

describe('lookTarget', () => {
  it('looks straight ahead when he appears, reads the cursor while the title is typed, held and erased, then looks ahead again', () => {
    expect(['1a', '1b', '1c', '1d', '1e', '3'].map(lookTarget)).toEqual(['center', 'cursor', 'cursor', 'cursor', 'center', 'center'])
  })

  it('follows the pointer outside the intro', () => {
    expect(lookTarget(undefined)).toBeNull()
  })
})

describe('bodyLean', () => {
  it('leans the body a third as far as the face, in whole art pixels', () => {
    expect(bodyLean({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 })
    expect(bodyLean({ x: GAZE_MAX.x, y: GAZE_MAX.y })).toEqual({ x: 2, y: 1 })
    expect(bodyLean({ x: -GAZE_MAX.x, y: -GAZE_MAX.y })).toEqual({ x: -2, y: -1 })
  })

  it('does not lean for a glance of one art pixel', () => {
    expect(bodyLean({ x: 1, y: 1 })).toEqual({ x: 0, y: 0 })
  })
})

describe('shadowOf', () => {
  it('stays put when the body does not lean', () => {
    expect(shadowOf({ x: 0, y: 0 })).toEqual({ shift: 0, stretch: 1 })
  })

  it('follows the lean and stretches with it, the same to either side', () => {
    const r = shadowOf({ x: 2, y: 0 }), l = shadowOf({ x: -2, y: 0 })
    expect(r.shift).toBeGreaterThan(0)
    expect(l.shift).toBe(-r.shift)
    expect(r.stretch).toBeGreaterThan(1)
    expect(l.stretch).toBe(r.stretch)
  })
})
