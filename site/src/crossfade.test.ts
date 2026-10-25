import { describe, expect, it } from 'vitest'
import { crossfade, settle } from './crossfade'

describe('crossfade', () => {
  it('starts with the state and nothing fading out', () => {
    expect(crossfade(undefined, 'idle')).toEqual({ cur: 'idle' })
  })

  it('keeps the same object when the state does not change', () => {
    const f = { cur: 'idle' as const }
    expect(crossfade(f, 'idle')).toBe(f)
  })

  it('fades the previous state out when the state changes', () => {
    expect(crossfade({ cur: 'typing' }, 'walking')).toEqual({ cur: 'walking', leaving: 'typing' })
  })

  it('drops the older sprite when the state changes again mid-fade', () => {
    expect(crossfade({ cur: 'walking', leaving: 'typing' }, 'slip_in')).toEqual({ cur: 'slip_in', leaving: 'walking' })
  })

  it('settle ends the fade and keeps the current state', () => {
    expect(settle({ cur: 'walking', leaving: 'typing' })).toEqual({ cur: 'walking' })
  })
})
