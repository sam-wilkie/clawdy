import { describe, expect, it } from 'vitest'
import type { Phase } from './flow'
import { phaseView } from './phase-view'

const phases: Phase[] = ['intro', 'stage', 'terminal', 'permission', 'plead', 'showcase', 'exit']

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
    expect(phaseView('stage').terminal).toBe(false)
  })

  it('shows the card only while asking', () => {
    expect(phases.filter((p) => phaseView(p).asking)).toEqual(['permission', 'plead'])
  })

  it('docks Vinnie on the drop zone, then beside the terminal, else at rest', () => {
    expect(phases.map((p) => phaseView(p).spot)).toEqual(['rest', 'rest', 'zone', 'terminal', 'terminal', 'rest', 'rest'])
  })

  it('keeps a fixed mood only on the exit screen (the others follow the mood timeline)', () => {
    expect(phaseView('exit').mood).toBe('cool')
    for (const p of ['intro', 'stage', 'terminal', 'permission', 'plead', 'showcase'] as const) expect(phaseView(p).mood).toBeUndefined()
  })

  it('hides Vinnie on the showcase page only', () => {
    expect(phases.filter((p) => phaseView(p).petHidden)).toEqual(['showcase'])
  })
})
