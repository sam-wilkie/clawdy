import { describe, expect, it } from 'vitest'
import { contains, dockOffset, dragOffset, feetOf } from './geometry'

const zone = { left: 230, top: 488, right: 358, bottom: 637 }

describe('contains', () => {
  it('is inclusive on the edges', () => {
    expect(contains(zone, 230, 488)).toBe(true)
    expect(contains(zone, 358, 637)).toBe(true)
  })
  it('rejects points outside', () => {
    expect(contains(zone, 229, 500)).toBe(false)
    expect(contains(zone, 300, 638)).toBe(false)
  })
})

describe('feetOf', () => {
  it('puts the feet at the horizontal centre and 89 % down the box', () => {
    expect(feetOf({ left: 514, top: 165, right: 765, bottom: 416 })).toEqual({ x: 639.5, y: 165 + 0.89 * 251 })
  })
})

describe('dockOffset', () => {
  it('moves the feet to the zone centre, lifted above its bottom edge', () => {
    expect(dockOffset({ x: 640, y: 388 }, zone, 40)).toEqual({ dx: 294 - 640, dy: 637 - 40 - 388 })
  })
})

describe('dragOffset', () => {
  const feet = { x: 640, y: 388 }
  const none = { dx: 0, dy: 0 }

  it('moves by the pointer delta', () => {
    expect(dragOffset(feet, none, { dx: 100, dy: -50 }, 1280, 720)).toEqual({ dx: 100, dy: -50 })
  })

  it('continues from where Vinnie was left', () => {
    expect(dragOffset(feet, { dx: 100, dy: -50 }, { dx: 20, dy: 10 }, 1280, 720)).toEqual({ dx: 120, dy: -40 })
  })

  it('keeps the feet inside the viewport', () => {
    expect(dragOffset(feet, none, { dx: 9999, dy: 9999 }, 1280, 720)).toEqual({ dx: 1280 - 8 - 640, dy: 720 - 8 - 388 })
    expect(dragOffset(feet, none, { dx: -9999, dy: -9999 }, 1280, 720)).toEqual({ dx: 8 - 640, dy: 80 - 388 })
  })
})
