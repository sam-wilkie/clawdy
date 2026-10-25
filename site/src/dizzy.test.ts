import { describe, expect, it } from 'vitest'
import { createShake, createSpin } from './dizzy'

const circle = (spin: ReturnType<typeof createSpin>, from: number, to: number, step: number, t0 = 0) => {
  let t = t0, fired = 0
  const dir = Math.sign(step)
  for (let a = from; dir > 0 ? a <= to : a >= to; a += step) {
    t += 16
    if (spin.push(200 + 100 * Math.cos(a), 200 + 100 * Math.sin(a), 200, 200, t)) fired++
  }
  return { fired, t }
}

describe('createSpin', () => {
  it('fires once after two full turns', () => {
    expect(circle(createSpin(), 0, 4.3 * Math.PI, 0.2).fired).toBe(1)
  })

  it('does not fire after one turn', () => {
    expect(circle(createSpin(), 0, 1.9 * Math.PI, 0.2).fired).toBe(0)
  })

  it('does not fire when the direction reverses', () => {
    const spin = createSpin()
    circle(spin, 0, 1.5 * Math.PI, 0.2)
    expect(circle(spin, 1.5 * Math.PI, -2.5 * Math.PI, -0.2, 1000).fired).toBe(0)
  })

  it('ignores a pointer jittering on the spot', () => {
    const spin = createSpin()
    let fired = 0
    for (let i = 0; i < 400; i++) if (spin.push(200 + (i % 2) * 5, 200 + (i % 3) * 5, 200, 200, i * 16)) fired++
    expect(fired).toBe(0)
  })

  it('starts over after a long pause', () => {
    const spin = createSpin()
    const first = circle(spin, 0, 1.9 * Math.PI, 0.2)
    expect(circle(spin, 0, 1.9 * Math.PI, 0.2, first.t + 2000).fired).toBe(0)
  })

  it('treats a teleport as a restart, not as circling', () => {
    const spin = createSpin()
    let fired = 0
    for (let i = 0; i < 80; i++) {
      const a = (i % 2) * Math.PI // jumps half a turn each event
      if (spin.push(200 + 100 * Math.cos(a), 200 + 100 * Math.sin(a), 200, 200, i * 16)) fired++
    }
    expect(fired).toBe(0)
  })
})

describe('createShake', () => {
  const run = (shake: ReturnType<typeof createShake>, moves: number[], gap = 100) =>
    moves.reduce((fired, dx, i) => fired + (shake.push(dx, i * gap) ? 1 : 0), 0)

  it('fires after three quick reversals', () => {
    expect(run(createShake(), [10, -10, 10, -10])).toBe(1)
  })

  it('does not fire on a steady drag in one direction', () => {
    expect(run(createShake(), [10, 12, 9, 15, 20, 11, 10])).toBe(0)
  })

  it('ignores slow wobbles under 6 px per move', () => {
    expect(run(createShake(), [5, -5, 5, -5, 5, -5, 5, -5])).toBe(0)
  })

  it('needs the reversals inside one second', () => {
    expect(run(createShake(), [10, -10, 10, -10], 600)).toBe(0)
  })

  it('needs three more reversals after firing', () => {
    expect(run(createShake(), [10, -10, 10, -10, 10, -10])).toBe(1) // 5 flips: fires at the 3rd, not again at the 5th
    expect(run(createShake(), [10, -10, 10, -10, 10, -10, 10])).toBe(2) // 6 flips: fires at the 3rd and the 6th
  })
})
