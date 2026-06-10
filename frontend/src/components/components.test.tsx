import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { makeForecast, makeRun, renderWithProviders } from '../test/helpers'
import { BrierSparkline } from './BrierSparkline'
import { EmptyState } from './EmptyState'
import { EventTimeline } from './EventTimeline'
import { ForecastComponentsPanel } from './ForecastComponentsPanel'
import { ReliabilityDiagram } from './ReliabilityDiagram'
import { TraceCanvas } from './TraceCanvas'
import { VitalsStrip } from './VitalsStrip'
import type { OutcomeCalibration, PolicyEvent } from '../lib/types'

describe('TraceCanvas', () => {
  const points = Array.from({ length: 60 }, (_, index) => ({
    step: index * 100,
    ts: '2026-06-09T12:00:00Z',
    value: 5 - index * 0.04,
  }))

  test('renders trace, target line, fan and an informative aria-label', () => {
    renderWithProviders(
      <TraceCanvas run={makeRun()} points={points} forecast={makeForecast()} showTarget />,
    )
    const svg = screen.getByRole('img')
    expect(svg.getAttribute('aria-label')).toContain('loss')
    expect(svg.getAttribute('aria-label')).toContain('P(hit target) 0.72')
    expect(svg.querySelectorAll('path[data-fan]')).toHaveLength(6)
  })

  test('renders without forecast or points', () => {
    renderWithProviders(
      <TraceCanvas run={makeRun({ latest_forecast: null })} points={[]} forecast={null} showTarget />,
    )
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('no loss data yet')
  })
})

describe('ForecastComponentsPanel', () => {
  test('shows family weights, features, and the calibrating badge', () => {
    render(<ForecastComponentsPanel forecast={makeForecast()} />)
    expect(screen.getByText('pow3')).toBeInTheDocument()
    expect(screen.getByText('z Δgrad')).toBeInTheDocument()
    expect(screen.getByText(/calibrating/)).toBeInTheDocument()
    expect(screen.getByText(/raw P\(hit\) 0.70/)).toBeInTheDocument()
  })

  test('calibrated badge when calibrated', () => {
    render(<ForecastComponentsPanel forecast={makeForecast({ calibrated: true })} />)
    expect(screen.getByText(/calibrated probabilities/)).toBeInTheDocument()
  })

  test('insufficient data message', () => {
    render(
      <ForecastComponentsPanel
        forecast={makeForecast({ components: { insufficient_data: true } })}
      />,
    )
    expect(screen.getByText(/Too few points/)).toBeInTheDocument()
  })
})

describe('EventTimeline', () => {
  const baseEvent: PolicyEvent = {
    id: 1,
    policy_id: 3,
    policy_name: 'kill-diverging',
    run_id: 7,
    run_name: 'doomed',
    kind: 'KILL_ISSUED',
    snapshot: { rule: { when: { signal: 'p_diverge' } }, signal_value: 0.93 },
    gross_recovered_usd: null,
    expected_recovered_usd: null,
    created_at: '2026-06-09T12:44:00Z',
  }

  test('renders kinds with details', () => {
    const events: PolicyEvent[] = [
      baseEvent,
      {
        ...baseEvent,
        id: 2,
        kind: 'KILL_ACKED',
        gross_recovered_usd: 500,
        expected_recovered_usd: 450,
      },
      { ...baseEvent, id: 3, kind: 'OVERRIDDEN', snapshot: {} },
    ]
    render(<EventTimeline events={events} />)
    expect(screen.getByText('KILL_ISSUED')).toBeInTheDocument()
    expect(screen.getByText('p_diverge 0.93')).toBeInTheDocument()
    expect(screen.getByText('$500 gross · $450 expected')).toBeInTheDocument()
    expect(screen.getByText(/kill cancelled/)).toBeInTheDocument()
  })

  test('empty state copy', () => {
    render(<EventTimeline events={[]} />)
    expect(screen.getByText(/No policy events yet/)).toBeInTheDocument()
  })
})

describe('ReliabilityDiagram and BrierSparkline', () => {
  const outcome: OutcomeCalibration = {
    outcome: 'hit_target',
    n_samples: 120,
    calibrated: true,
    brier_raw: 0.21,
    brier_calibrated: 0.16,
    fitted_at: '2026-06-09T12:00:00Z',
    bins: Array.from({ length: 10 }, (_, index) => ({
      bin_low: index / 10,
      bin_high: (index + 1) / 10,
      count: index % 3 === 0 ? 0 : 12,
      mean_forecast: index / 10 + 0.05,
      observed_rate: index / 10,
    })),
    history: [
      { fitted_at: '2026-06-08T12:00:00Z', brier_after: 0.2, n_samples: 90 },
      { fitted_at: '2026-06-09T12:00:00Z', brier_after: 0.16, n_samples: 120 },
    ],
  }

  test('diagram renders occupied bins', () => {
    render(<ReliabilityDiagram outcome={outcome} />)
    const svg = screen.getByRole('img')
    expect(svg.getAttribute('aria-label')).toContain('120 samples')
    expect(svg.querySelectorAll('circle').length).toBeGreaterThan(3)
  })

  test('sparkline renders with history and degrades without', () => {
    const { rerender } = render(<BrierSparkline history={outcome.history} />)
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('2 refits')
    rerender(<BrierSparkline history={[]} />)
    expect(screen.getByText(/history grows/)).toBeInTheDocument()
  })
})

describe('VitalsStrip and EmptyState', () => {
  test('vitals aggregate live runs', () => {
    const runs = [
      makeRun({ id: 1, burn_usd_per_hour: 20 }),
      makeRun({ id: 2, burn_usd_per_hour: 6, health: 'AT_RISK' }),
      makeRun({ id: 3, status: 'COMPLETED', health: null }),
    ]
    renderWithProviders(<VitalsStrip runs={runs} ledger={undefined} />)
    expect(screen.getByText('2 · 1 at risk')).toBeInTheDocument()
    expect(screen.getByText('$26/hr')).toBeInTheDocument()
  })

  test('empty state shows title and hint', () => {
    render(<EmptyState title="Nothing here" hint="Do the thing." />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.getByText('Do the thing.')).toBeInTheDocument()
  })
})
