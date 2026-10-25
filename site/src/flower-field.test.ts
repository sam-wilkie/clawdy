import { describe, expect, it } from 'vitest'
import { buildFlowers } from './flower-field'

const center = { x: 294, y: 563 }

describe('buildFlowers', () => {
  const flowers = buildFlowers(center, 104, 37)

  it('fills a patch around the centre', () => expect(flowers.length).toBeGreaterThan(10))

  it('keeps every flower inside the radius, on the centre of a grid cell', () => {
    for (const f of flowers) {
      expect(Math.hypot(f.x - center.x, f.y - center.y)).toBeLessThan(104)
      expect((f.x - 18.5) % 37).toBe(0)
      expect((f.y - 18.5) % 37).toBe(0)
    }
  })

  it('is deterministic', () => expect(buildFlowers(center, 104, 37)).toEqual(flowers))

  it('is stronger near the centre than at the rim', () => {
    const d = (f: (typeof flowers)[number]) => Math.hypot(f.x - center.x, f.y - center.y)
    const sorted = [...flowers].sort((a, b) => d(a) - d(b))
    expect(sorted[0].alpha).toBeGreaterThan(sorted[sorted.length - 1].alpha)
  })
})
