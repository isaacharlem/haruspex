import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test } from 'vitest'
import { makeRun, mockFetch, renderWithProviders } from '../test/helpers'
import { CalibrationPage } from './CalibrationPage'
import { FleetPage } from './FleetPage'
import { LedgerPage } from './LedgerPage'

const EMPTY_CALIBRATION = {
  min_samples: 30,
  outcomes: [
    {
      outcome: 'hit_target',
      n_samples: 0,
      calibrated: false,
      brier_raw: null,
      brier_calibrated: null,
      fitted_at: null,
      bins: [],
      history: [],
    },
    {
      outcome: 'diverge',
      n_samples: 0,
      calibrated: false,
      brier_raw: null,
      brier_calibrated: null,
      fitted_at: null,
      bins: [],
      history: [],
    },
  ],
}

describe('FleetPage', () => {
  beforeEach(() => {
    mockFetch({
      '/runs?': { items: [makeRun(), makeRun({ id: 2, status: 'COMPLETED', health: null })], next_cursor: null },
      '/runs/1/metrics': { run_id: 1, name: 'loss', total_points: 0, points: [] },
      '/runs/2/metrics': { run_id: 2, name: 'loss', total_points: 0, points: [] },
      '/ledger': {
        window_days: 30,
        gross_recovered_usd: 1284,
        expected_recovered_usd: 1166,
        kills: 2,
        rows: [],
      },
    })
  })

  test('renders vitals and run cards with live runs first', async () => {
    renderWithProviders(<FleetPage />)
    await waitFor(() => expect(screen.getAllByTestId('run-card')).toHaveLength(2))
    expect(screen.getByText('Fleet burn')).toBeInTheDocument()
    expect(screen.getByText('$1,284 gross · $1,166 expected')).toBeInTheDocument()
    expect(screen.getByText('Concluded')).toBeInTheDocument()
  })
})

describe('LedgerPage', () => {
  beforeEach(() => {
    mockFetch({
      '/ledger': {
        window_days: 30,
        gross_recovered_usd: 500,
        expected_recovered_usd: 450,
        kills: 1,
        rows: [
          {
            run_id: 7,
            run_name: 'doomed-run',
            killed_at: '2026-06-09T12:00:00Z',
            gpu_type: 'H100',
            gpu_count: 8,
            gpu_hourly_usd: 2.5,
            gross_recovered_usd: 500,
            expected_recovered_usd: 450,
          },
        ],
      },
    })
  })

  test('shows both totals, honestly labeled, and rows', async () => {
    renderWithProviders(<LedgerPage />)
    await waitFor(() => expect(screen.getByText('doomed-run')).toBeInTheDocument())
    expect(screen.getByText('Gross freed compute')).toBeInTheDocument()
    expect(screen.getByText('Expected value, forecast-weighted')).toBeInTheDocument()
    // Totals in the header and per-row figures both render.
    expect(screen.getAllByText('$500')).toHaveLength(2)
    expect(screen.getAllByText('$450')).toHaveLength(2)
  })
})

describe('CalibrationPage', () => {
  test('renders the calibrating empty state', async () => {
    mockFetch({ '/calibration': EMPTY_CALIBRATION })
    renderWithProviders(<CalibrationPage />)
    await waitFor(() =>
      expect(screen.getByText('No completed runs to calibrate against')).toBeInTheDocument(),
    )
  })
})
