import { describe, expect, it } from 'vitest'
import { initialFlow, reduce, wantsIntro, type Flow } from './flow'

const at = (phase: Flow['phase'], denies = 0): Flow => ({ phase, denies })

describe('wantsIntro', () => {
  it('plays on every load', () => expect(wantsIntro({ reduced: false, skip: false })).toBe(true))
  it('can be skipped with ?intro=0', () => expect(wantsIntro({ reduced: false, skip: true })).toBe(false))
  it('never plays under reduced motion', () => expect(wantsIntro({ reduced: true, skip: false })).toBe(false))
})

describe('flow', () => {
  it('starts at the intro or straight at the stage', () => {
    expect(initialFlow(true)).toEqual(at('intro'))
    expect(initialFlow(false)).toEqual(at('stage'))
  })

  it('walks the happy path to the showcase, through the allow choreography', () => {
    let f = initialFlow(true)
    for (const type of ['introDone', 'dropped', 'terminalReady', 'allow'] as const) f = reduce(f, { type })
    expect(f).toEqual(at('allowing'))
    expect(reduce(f, { type: 'allowed' })).toEqual(at('showcase'))
  })

  it('does not let a click interrupt the allow choreography', () => {
    for (const type of ['allow', 'deny', 'restart'] as const) {
      expect(reduce(at('allowing'), type === 'restart' ? { type, intro: true } : { type })).toEqual(at('allowing'))
    }
  })

  it('pleads on the first deny and ends on the second', () => {
    const plead = reduce(at('permission'), { type: 'deny' })
    expect(plead).toEqual(at('plead', 1))
    expect(reduce(plead, { type: 'deny' })).toEqual(at('exit', 2))
  })

  it('still lets the plea end in Allow', () => {
    expect(reduce(at('plead', 1), { type: 'allow' })).toEqual(at('allowing', 1))
  })

  it('restarts from the showcase or the exit screen on the intro, with a clean count', () => {
    expect(reduce(at('showcase', 1), { type: 'restart', intro: true })).toEqual(at('intro'))
    expect(reduce(at('exit', 2), { type: 'restart', intro: true })).toEqual(at('intro'))
  })

  it('restarts straight on the stage when there is no intro (reduced motion)', () => {
    expect(reduce(at('exit', 2), { type: 'restart', intro: false })).toEqual(at('stage'))
  })

  it('ignores an action that does not belong to the current phase', () => {
    expect(reduce(at('stage'), { type: 'allow' })).toEqual(at('stage'))
    expect(reduce(at('permission'), { type: 'allowed' })).toEqual(at('permission'))
    expect(reduce(at('intro'), { type: 'dropped' })).toEqual(at('intro'))
    expect(reduce(at('terminal'), { type: 'deny' })).toEqual(at('terminal'))
    expect(reduce(at('stage'), { type: 'restart', intro: true })).toEqual(at('stage'))
  })
})
