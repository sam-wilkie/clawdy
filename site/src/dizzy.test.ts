import { describe, expect, it } from 'vitest'
import { createSpin } from './dizzy'

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
