import type { VinnieState } from './vinnie-states'

export const SHOWCASE_SUBTITLE = 'Un poco de compañía para tu día de código.'
export const EXIT_LINE = 'Gracias por la visita.'

export const CARDS: { state: VinnieState; label: string }[] = [
  { state: 'debugger', label: 'Leyendo' },
  { state: 'thinking', label: 'Pensando' },
  { state: 'typing', label: 'Escribiendo' },
  { state: 'wizard', label: 'Mago' },
  { state: 'grooving', label: '1 subagente' },
  { state: 'juggling', label: '2+ subagentes' },
]
