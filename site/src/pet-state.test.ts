import { describe, expect, it } from 'vitest'
import { petReduce, type PetEvent, type PetState } from './pet-state'

const step = (s: PetState, e: PetEvent) => petReduce(s, e)

describe('petReduce', () => {
  it('cheers up on a click, also when asleep', () => {
    expect(step('idle', 'click')).toBe('happy')
    expect(step('sleeping', 'click')).toBe('happy')
    expect(step('wake', 'click')).toBe('happy')
  })

  it('gets dizzy from a spin and cannot be interrupted while dizzy', () => {
    for (const s of ['idle', 'happy', 'wake', 'walking'] as const) expect(step(s, 'spin')).toBe('dizzy')
    expect(step('dizzy', 'click')).toBe('dizzy')
    expect(step('dizzy', 'spin')).toBe('dizzy')
    expect(step('dizzy', 'sleep')).toBe('dizzy')
  })

  it('falls asleep only from idle', () => {
    expect(step('idle', 'sleep')).toBe('sleeping')
    expect(step('happy', 'sleep')).toBe('happy')
  })

  it('wakes up on activity, only from sleeping', () => {
    expect(step('sleeping', 'activity')).toBe('wake')
    expect(step('idle', 'activity')).toBe('idle')
  })

  it('settles back to idle when a timed state ends', () => {
    for (const s of ['happy', 'dizzy', 'wake', 'walking'] as const) expect(step(s, 'settle')).toBe('idle')
    expect(step('sleeping', 'settle')).toBe('sleeping')
  })
})
