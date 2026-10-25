import { describe, expect, it } from 'vitest'
import { moodAt, moodTimeline } from './mood-timeline'

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
