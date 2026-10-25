/** Vinnie's animated SVGs (copied from desktop/renderer/assets/monster). vb is each file's viewBox. */
type Box = [number, number, number, number]
const std: Box = [-15, -25, 45, 45]
const entry = (name: string, vb: Box = std) => ({ src: `/vinnie/${name}.svg`, vb })

export const VINNIE = {
  idle: entry('idle'),
  walking: entry('walking'),
  wake: entry('wake'),
  sleeping: entry('sleeping', [-10, -20, 40, 40]),
  dizzy: entry('dizzy'),
  happy: entry('happy', [-12, -15, 40, 40]),
  thinking: entry('thinking'),
  typing: entry('typing'),
  wizard: entry('wizard'),
  grooving: entry('grooving'),
  juggling: entry('juggling'),
  debugger: entry('debugger'),
  alert: entry('alert'),
  error: entry('error'),
  idea: entry('idea'),
  slip_in: entry('slip-in'),   // slides under the terminal window's left edge (drawn for a window edge at viewBox x = 16)
  peek: entry('peek'),         // slides out at the window's right edge, waves a mitten, blinks and holds half out (edge at viewBox x = 0)
  jump: entry('jump'),         // 350 ms squash and stretch drawn at the resting spot; the arc itself is CSS (.jumping)
  waiting_reply: entry('waiting_reply'),
  cool: entry('cool'),
} as const

export type VinnieState = keyof typeof VINNIE

/** Fetch every animation up front, so the first swap (a click, a drag) never waits on the network. */
export function preloadVinnie(): void {
  for (const { src } of Object.values(VINNIE)) new Image().src = src
}
