import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { VINNIE, type VinnieState } from './vinnie-states'

describe('vinnie states', () => {
  it.each(Object.keys(VINNIE) as VinnieState[])('%s points at a file whose viewBox matches the table', (name) => {
    const svg = readFileSync(new URL(`../public${VINNIE[name].src}`, import.meta.url), 'utf8')
    const vb = /viewBox="([^"]+)"/.exec(svg)?.[1].split(/\s+/).map(Number)
    expect(vb).toEqual(VINNIE[name].vb)
  })
})
