import { describe, expect, it } from 'vitest'
import { JUMP_MS, moodAt, moodTimeline } from './mood-timeline'
import { T } from './terminal-script'

describe('moodTimeline', () => {
  it('shows the idea bulb when the card arrives, then waits for the answer', () => {
    expect(moodTimeline('permission').map((b) => b.mood)).toEqual(['idea', 'waiting_reply'])
  })

  it('shows the error, wakes up, scratches his head, pleads with hearts, then waits for another answer', () => {
    expect(moodTimeline('plead').map((b) => b.mood)).toEqual(['error', 'wake', 'scratch', 'aegyo', 'waiting_reply'])
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

  it('crosses hidden under the window, peeks out at the right edge, then jumps to its resting spot', () => {
    expect(moodTimeline('terminal', 'tool').map((b) => b.mood)).toEqual(['slip_in', 'peek', 'jump'])
  })

  it('leaves the tool stage long enough for the slip-in, the peek and the jump', () => {
    const total = moodTimeline('terminal', 'tool').reduce((t, b) => t + (b.ms ?? JUMP_MS), 0)
    expect(total).toBeLessThanOrEqual(T.tool)
  })

  it('holds the jump until the stage ends, so the card finds him landed', () => {
    expect(moodTimeline('terminal', 'tool').at(-1)?.ms).toBeUndefined()
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
    expect(moodAt(plead, 1199)).toBe('error')
    expect(moodAt(plead, 1200)).toBe('wake')
    expect(moodAt(plead, 2699)).toBe('wake')
    expect(moodAt(plead, 2700)).toBe('scratch')
    expect(moodAt(plead, 3450)).toBe('aegyo')
    expect(moodAt(plead, 9529)).toBe('aegyo')
    expect(moodAt(plead, 9530)).toBe('waiting_reply')
    expect(moodAt(plead, 600000)).toBe('waiting_reply')
  })

  it('is undefined without beats', () => expect(moodAt([], 100)).toBeUndefined())
})
