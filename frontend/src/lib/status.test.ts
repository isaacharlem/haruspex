import { describe, expect, test } from 'vitest'
import { bySeverity, statusVisual } from './status'
import { makeRun } from '../test/helpers'

describe('statusVisual', () => {
  test('running runs map health to sigil and color', () => {
    expect(statusVisual('RUNNING', 'HEALTHY')).toMatchObject({
      sigil: 'circle',
      label: 'HEALTHY',
    })
    expect(statusVisual('RUNNING', 'AT_RISK')).toMatchObject({
      sigil: 'triangle',
      label: 'AT RISK',
    })
    expect(statusVisual('RUNNING', 'DOOMED')).toMatchObject({ sigil: 'saltire', label: 'DOOMED' })
    expect(statusVisual('RUNNING', null).label).toBe('AUGURING')
  })

  test('terminal statuses have their own sigils', () => {
    expect(statusVisual('COMPLETED', null).sigil).toBe('diamond')
    expect(statusVisual('KILLED', null).sigil).toBe('slashed')
    expect(statusVisual('DIVERGED', null).label).toBe('DIVERGED')
    expect(statusVisual('LOST', null).sigil).toBe('dotted')
  })
})

describe('bySeverity', () => {
  test('live runs come first, doomed before healthy', () => {
    const healthy = makeRun({ id: 1, health: 'HEALTHY' })
    const doomed = makeRun({ id: 2, health: 'DOOMED' })
    const done = makeRun({ id: 3, status: 'COMPLETED', health: null })
    const sorted = [done, healthy, doomed].sort(bySeverity)
    expect(sorted.map((run) => run.id)).toEqual([2, 1, 3])
  })
})
