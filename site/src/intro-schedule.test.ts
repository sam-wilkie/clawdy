import { describe, expect, it } from 'vitest'
import { introFrames, introDuration, readSeen, markSeen } from './intro-schedule'

describe('introFrames', () => {
  it('runs the frames in order', () => {
    expect(introFrames('Clawdy').map((f) => f.frame)).toEqual(['1a', '1b', '1c', '1d', '1e', '3'])
  })

  it('sizes typing, flashing and deleting from the title length', () => {
    const ms = Object.fromEntries(introFrames('Clawdy').map((f) => [f.frame, f.ms]))
    expect(ms['1b']).toBe(6 * 100)
    expect(ms['1c']).toBe(2 * 250)
    expect(ms['1d']).toBe(6 * 50 + 200)
  })

  it('lasts 6.2 s with the default title', () => expect(introDuration('Clawdy')).toBe(6200))
})

describe('seen flag', () => {
  it('is false when storage is unavailable and never throws', () => {
    expect(readSeen()).toBe(false)
    expect(() => markSeen()).not.toThrow()
  })
})
