import { describe, expect, it } from 'vitest'
import { PROMPT, TOOL_COMMAND, stageIndex, terminalFrames, type TerminalStage } from './terminal-script'

describe('terminalFrames', () => {
  it('goes from typing to the tool prompt, in order', () => {
    expect(terminalFrames('hola').map((f) => f.stage)).toEqual(['type', 'sent', 'think', 'tool'])
  })

  it('types the prompt at 55 ms a character', () => {
    expect(terminalFrames('hola')[0].ms).toBe(4 * 55)
    expect(terminalFrames(PROMPT)[0].ms).toBe(PROMPT.length * 55)
  })
})

describe('stageIndex', () => {
  it('orders the stages so the view can ask "has it reached X"', () => {
    const order: TerminalStage[] = ['type', 'sent', 'think', 'tool', 'ready']
    expect(order.map(stageIndex)).toEqual([0, 1, 2, 3, 4])
  })
})

describe('copy', () => {
  it('asks to clone the repo shown on the page and runs that exact command', () => {
    expect(PROMPT).toContain('https://github.com/sam-wilkie/clawdy')
    expect(TOOL_COMMAND).toBe('git clone https://github.com/sam-wilkie/clawdy.git')
  })
})
