export type TerminalStage = 'type' | 'sent' | 'think' | 'tool' | 'ready'
const ORDER: TerminalStage[] = ['type', 'sent', 'think', 'tool', 'ready']
export const stageIndex = (s: TerminalStage) => ORDER.indexOf(s)

export const PROMPT = 'Clona https://github.com/sam-wilkie/clawdy y ayúdame a instalarlo'
export const TOOL_COMMAND = 'git clone https://github.com/sam-wilkie/clawdy.git'

// ms. The prompt types out, is sent, the agent thinks, then asks to run a tool ('ready' = the card is up).
// think and tool are long enough for Vinnie to slip under the window (650 ms walk + 1.45 s sprite) and to come out again.
export const T = { typeChar: 55, sent: 400, think: 2200, tool: 2200 }

export function terminalFrames(prompt: string = PROMPT): { stage: TerminalStage; ms: number }[] {
  return [
    { stage: 'type', ms: prompt.length * T.typeChar },
    { stage: 'sent', ms: T.sent },
    { stage: 'think', ms: T.think },
    { stage: 'tool', ms: T.tool },
  ]
}
