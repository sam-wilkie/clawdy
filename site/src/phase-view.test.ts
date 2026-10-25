import { describe, expect, it } from 'vitest'
import type { Phase } from './flow'
import { phaseView } from './phase-view'

const phases: Phase[] = ['intro', 'stage', 'terminal', 'permission', 'plead', 'allowing', 'showcase', 'exit']

describe('phaseView', () => {
  it('flags exactly one screen family per phase', () => {
    for (const p of phases) {
      const v = phaseView(p)
      expect([v.intro, v.stage, v.terminal, v.showcase, v.exit].filter(Boolean)).toHaveLength(1)
    }
  })

  it('keeps the terminal on screen while it asks for permission', () => {
    expect(phaseView('terminal').terminal).toBe(true)
    expect(phaseView('permission').terminal).toBe(true)
    expect(phaseView('plead').terminal).toBe(true)
    expect(phaseView('allowing').terminal).toBe(true) // it shrinks away after the card fades
    expect(phaseView('stage').terminal).toBe(false)
  })

  it('shows the card only while asking', () => {
    expect(phases.filter((p) => phaseView(p).asking)).toEqual(['permission', 'plead'])
  })

  it('docks Vinnie on the drop zone, then beside the terminal, else at rest', () => {
    expect(phases.map((p) => phaseView(p).spot)).toEqual(['rest', 'rest', 'zone', 'terminal', 'terminal', 'terminal', 'rest', 'rest'])
  })

  it('keeps a fixed mood only on the exit screen (the others follow the mood timeline)', () => {
    expect(phaseView('exit').mood).toBe('cool')
    for (const p of ['intro', 'stage', 'terminal', 'permission', 'plead', 'allowing', 'showcase'] as const) expect(phaseView(p).mood).toBeUndefined()
  })

  it('marks the allow choreography, where the card is still on screen but no longer answerable', () => {
    expect(phases.filter((p) => phaseView(p).allowing)).toEqual(['allowing'])
    expect(phaseView('allowing').asking).toBe(false)
  })

  it('hides Vinnie on the showcase page only', () => {
    expect(phases.filter((p) => phaseView(p).petHidden)).toEqual(['showcase'])
  })

  it('while the terminal runs: types on the drop zone, slips behind the window, then comes out', () => {
    expect(phaseView('terminal', 'type').spot).toBe('zone')
    expect(phaseView('terminal', 'sent').spot).toBe('zone')
    expect(phaseView('terminal', 'think').spot).toBe('hide')
    expect(phaseView('terminal', 'tool').spot).toBe('terminal')
    expect(phaseView('terminal', 'think').behind).toBe(true)
    expect(phaseView('terminal', 'tool').behind).toBe(true)
    expect(phaseView('terminal', 'sent').behind).toBe(false)
    expect(phaseView('permission').behind).toBe(false)
  })

  it('on a narrow screen there is no window edge to hide behind: straight to the waiting spot', () => {
    const v = phaseView('terminal', 'think', true)
    expect(v.spot).toBe('terminal')
    expect(v.behind).toBe(false)
  })
})
