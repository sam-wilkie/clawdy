export type PetState = 'idle' | 'happy' | 'dizzy' | 'sleeping' | 'wake' | 'walking'
export type PetEvent = 'click' | 'spin' | 'sleep' | 'activity' | 'settle'

// ms. A timed state returns to idle with 'settle'; idle falls asleep after IDLE; a dizzy spell is followed by a cooldown.
export const DURATION = { happy: 2400, dizzy: 6000, wake: 1600, walking: 1600, cooldown: 4000, idle: 25000 }

export function petReduce(s: PetState, e: PetEvent): PetState {
  if (s === 'dizzy' && e !== 'settle') return s // dizzy cannot be interrupted
  switch (e) {
    case 'click': return 'happy'
    case 'spin': return 'dizzy'
    case 'sleep': return s === 'idle' ? 'sleeping' : s
    case 'activity': return s === 'sleeping' ? 'wake' : s
    case 'settle': return s === 'sleeping' || s === 'idle' ? s : 'idle'
  }
}
