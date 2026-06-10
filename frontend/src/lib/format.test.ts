import { describe, expect, test } from 'vitest'
import { fmtMetric, fmtPercent, fmtProb, fmtRate, fmtStep, fmtUsd } from './format'

describe('format', () => {
  test('probabilities render to two decimals', () => {
    expect(fmtProb(0.041)).toBe('0.04')
    expect(fmtProb(1)).toBe('1.00')
    expect(fmtProb(null)).toBe('—')
  })

  test('dollars render whole with separators', () => {
    expect(fmtUsd(1284.4)).toBe('$1,284')
    expect(fmtUsd(0)).toBe('$0')
    expect(fmtUsd(null)).toBe('—')
  })

  test('steps compact', () => {
    expect(fmtStep(950)).toBe('950')
    expect(fmtStep(4_100)).toBe('4.1k')
    expect(fmtStep(10_000)).toBe('10k')
    expect(fmtStep(2_500_000)).toBe('2.5M')
  })

  test('metric values stay readable across scales', () => {
    expect(fmtMetric(3.14159)).toBe('3.142')
    expect(fmtMetric(1e-6)).toBe('1.00e-6')
    expect(fmtMetric(Number.NaN)).toBe('—')
  })

  test('rates and percents', () => {
    expect(fmtRate(20)).toBe('$20/hr')
    expect(fmtRate(2.5)).toBe('$2.50/hr')
    expect(fmtPercent(0.4)).toBe('40%')
  })
})
