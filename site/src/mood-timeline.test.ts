import { describe, expect, it } from 'vitest'
import { moodAt, moodTimeline } from './mood-timeline'
import { T } from './terminal-script'

describe('moodTimeline', () => {
  it('shows the idea bulb when the card arrives, then waits for the answer', () => {
    expect(moodTimeline('permission').map((b) => b.mood)).toEqual(['idea', 'waiting_reply'])
  })

  it('shows the error, then wakes up, then waits for another answer', () => {
    expect(moodTimeline('plead').map((b) => b.mood)).toEqual(['error', 'wake', 'waiting_reply'])
  })

  it('has nothing to say in the other phases, and the last beat holds forever', () => {
    for (const p of ['intro', 'stage', 'terminal', 'showcase', 'exit'] as const) expect(moodTimeline(p)).toEqual([])
    for (const p of ['permission', 'plead'] as const) expect(moodTimeline(p).at(-1)?.ms).toBeUndefined()
  })
})

describe('moodTimeline while the terminal runs', () => {
  it('has nothing while it types', () => {
    expect(moodTimeline('terminal', 'type')).toEqual([])
    expect(moodTimeline('terminal', 'sent')).toEqual([])
  })

  it('walks to the window edge and slips in while the agent thinks', () => {
    expect(moodTimeline('terminal', 'think').map((b) => b.mood)).toEqual(['walking', 'slip_in'])
  })

  it('crosses hidden under the window, peeks out at the right edge looking around, then slips out', () => {
    expect(moodTimeline('terminal', 'tool').map((b) => b.mood)).toEqual(['slip_in', 'peek', 'slip_out'])
  })

  it('leaves the tool stage long enough for the whole slip-in, peek and slip-out', () => {
    const beats = moodTimeline('terminal', 'tool')
    const before = beats.slice(0, -1).reduce((t, b) => t + (b.ms ?? 0), 0)
    expect(before + 1450).toBeLessThanOrEqual(T.tool)
  })

  it('on a narrow screen it just walks to the waiting spot', () => {
    expect(moodTimeline('terminal', 'think', true).map((b) => b.mood)).toEqual(['walking'])
    expect(moodTimeline('terminal', 'tool', true).map((b) => b.mood)).toEqual(['walking'])
  })
})

describe('moodAt', () => {
  const plead = moodTimeline('plead')

  it('walks the beats by elapsed time', () => {
    expect(moodAt(plead, 0)).toBe('error')
    expect(moodAt(plead, 2199)).toBe('error')
    expect(moodAt(plead, 2200)).toBe('wake')
    expect(moodAt(plead, 3799)).toBe('wake')
    expect(moodAt(plead, 3800)).toBe('waiting_reply')
    expect(moodAt(plead, 600000)).toBe('waiting_reply')
  })

  it('is undefined without beats', () => expect(moodAt([], 100)).toBeUndefined())
})
