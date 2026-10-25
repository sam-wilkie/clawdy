import { describe, expect, it } from 'vitest'
import { CARDS, EXIT_LINE, SHOWCASE_SUBTITLE } from './showcase-data'
import { VINNIE } from './vinnie-states'

describe('showcase cards', () => {
  it('has the six cards of the flow, in order', () => {
    expect(CARDS.map((c) => c.state)).toEqual(['debugger', 'thinking', 'typing', 'wizard', 'grooving', 'juggling'])
  })

  it('uses only Vinnie states that ship an animation, with unique captions', () => {
    for (const c of CARDS) expect(VINNIE).toHaveProperty(c.state)
    expect(new Set(CARDS.map((c) => c.label)).size).toBe(CARDS.length)
  })

  it('captions the last two cards as subagents', () => {
    expect(CARDS[4].label).toBe('1 subagente')
    expect(CARDS[5].label).toBe('2+ subagentes')
  })
})

describe('copy', () => {
  it('has a subtitle and a farewell line', () => {
    expect(SHOWCASE_SUBTITLE.length).toBeGreaterThan(10)
    expect(EXIT_LINE).toBe('Gracias por la visita.')
  })
})
