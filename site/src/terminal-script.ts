export type TerminalStage = 'type' | 'sent' | 'think' | 'tool' | 'ready'
const ORDER: TerminalStage[] = ['type', 'sent', 'think', 'tool', 'ready']
export const stageIndex = (s: TerminalStage) => ORDER.indexOf(s)

export const PROMPT = 'Clona https://github.com/sam-wilkie/clawdy y ayúdame a instalarlo'
export const TOOL_COMMAND = 'git clone https://github.com/sam-wilkie/clawdy.git'

// ms. The prompt types out, is sent, the agent thinks, then asks to run a tool ('ready' = the card is up).
// think is long enough for Vinnie to walk (650 ms) and slip under the window (1.45 s sprite); tool for him to cross hidden
// (650 ms), peek out and look around (2.4 s) and come out (1.45 s).
export const T = { typeChar: 55, sent: 400, think: 2200, tool: 4600 }

export function terminalFrames(prompt: string = PROMPT): { stage: TerminalStage; ms: number }[] {
  return [
    { stage: 'type', ms: prompt.length * T.typeChar },
    { stage: 'sent', ms: T.sent },
    { stage: 'think', ms: T.think },
    { stage: 'tool', ms: T.tool },
  ]
}
