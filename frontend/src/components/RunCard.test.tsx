import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, test } from 'vitest'
import { makeForecast, makeRun, mockFetch, renderWithProviders } from '../test/helpers'
import { RunCard } from './RunCard'

beforeEach(() => {
  mockFetch({ '/metrics': { run_id: 1, name: 'loss', total_points: 0, points: [] } })
})

describe('RunCard status rendering', () => {
  test('healthy run shows sigil label and P(hit target)', () => {
    renderWithProviders(<RunCard run={makeRun()} />)
    expect(screen.getByText('HEALTHY')).toBeInTheDocument()
    expect(screen.getByText(/P\(hit target\)/)).toBeInTheDocument()
    expect(screen.getByText('0.72')).toBeInTheDocument()
    expect(screen.getByText('$20/hr')).toBeInTheDocument()
  })

  test('doomed run leads with P(diverge)', () => {
    const run = makeRun({
      health: 'DOOMED',
      latest_forecast: makeForecast({ p_hit_target: 0.02, p_diverge: 0.93 }),
    })
    renderWithProviders(<RunCard run={run} />)
    expect(screen.getByText('DOOMED')).toBeInTheDocument()
    expect(screen.getByText(/P\(diverge\)/)).toBeInTheDocument()
    expect(screen.getByText('0.93')).toBeInTheDocument()
  })

  test('killed run is dimmed and labeled', () => {
    const run = makeRun({ status: 'KILLED', health: null })
    renderWithProviders(<RunCard run={run} />)
    expect(screen.getByText('KILLED')).toBeInTheDocument()
    expect(screen.getByTestId('run-card').className).toContain('opacity-60')
  })

  test('uncalibrated forecast carries the calibrating mark', () => {
    renderWithProviders(<RunCard run={makeRun()} />)
    expect(screen.getByText('~cal')).toBeInTheDocument()
  })

  test('forecastless run shows a placeless dash', () => {
    renderWithProviders(<RunCard run={makeRun({ latest_forecast: null, health: null })} />)
    expect(screen.getByText('AUGURING')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
