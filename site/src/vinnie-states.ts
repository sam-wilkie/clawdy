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
  slip_out: entry('slip-out'), // comes out from under its right edge (window edge at viewBox x = 0), ends in the idle pose
  peek: entry('peek'),         // pokes out at the window's right edge, looks left, right, up, blinks, hides again (edge at viewBox x = 0)
  waiting_reply: entry('waiting_reply'),
  cool: entry('cool'),
} as const

export type VinnieState = keyof typeof VINNIE

/** Fetch every animation up front, so the first swap (a click, a drag) never waits on the network. */
export function preloadVinnie(): void {
  for (const { src } of Object.values(VINNIE)) new Image().src = src
}
