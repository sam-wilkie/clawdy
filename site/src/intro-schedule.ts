export type IntroFrame = '1a' | '1b' | '1c' | '1d' | '1e' | '3'
export const TITLE = 'Clawdy'

// ms. 1a cursor only, 1b type, 1c flash, 1d delete, 1e centre (matches the CSS move), 3 iris + panic.
export const T = { cursorOnly: 500, typeForward: 100, flashDur: 250, flashCount: 2, typeReverse: 50, afterDelete: 200, centerMove: 600, react: 3500 }

export function introFrames(title: string = TITLE): { frame: IntroFrame; ms: number }[] {
  return [
    { frame: '1a', ms: T.cursorOnly },
    { frame: '1b', ms: title.length * T.typeForward },
    { frame: '1c', ms: T.flashCount * T.flashDur },
    { frame: '1d', ms: title.length * T.typeReverse + T.afterDelete },
    { frame: '1e', ms: T.centerMove },
    { frame: '3', ms: T.react },
  ]
}

export const introDuration = (title: string = TITLE) => introFrames(title).reduce((n, f) => n + f.ms, 0)
