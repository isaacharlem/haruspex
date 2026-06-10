import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, test } from 'vitest'
import { makeRun, mockFetch, renderWithProviders } from '../test/helpers'
import { RunDetailPage } from './RunDetailPage'

function renderDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunDetailPage />} />
    </Routes>,
    { route: '/runs/1' },
  )
}

describe('RunDetailPage', () => {
  beforeEach(() => {
    mockFetch({
      '/runs/1/metrics': {
        run_id: 1,
        name: 'loss',
        total_points: 800,
        points: [
          { step: 0, ts: '2026-06-09T10:00:00Z', value: 5.2 },
          { step: 4100, ts: '2026-06-09T12:00:00Z', value: 3.4 },
        ],
      },
      '/events': { items: [], next_cursor: null },
      '/runs/1': makeRun(),
    })
  })

  test('renders header, prognosis numerals, and components panel', async () => {
    renderDetail()
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'gpt2-small-bf16' })).toBeInTheDocument(),
    )
    expect(screen.getByText('P(hit target)')).toBeInTheDocument()
    expect(screen.getByText('0.72')).toBeInTheDocument()
    expect(screen.getByText('HEALTHY')).toBeInTheDocument()
    expect(screen.getByText(/8×H100/)).toBeInTheDocument()
    expect(screen.getByText('Forecast components')).toBeInTheDocument()
    expect(screen.getByText(/No policy events yet/)).toBeInTheDocument()
    expect(screen.getByText(/2 of 800 points/)).toBeInTheDocument()
  })

  test('kill button opens the confirm dialog', async () => {
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('kill-button')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('kill-button'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByTestId('confirm-kill')).toBeDisabled()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('metric tabs switch the requested series', async () => {
    const fetchMock = mockFetch({
      '/runs/1/metrics': { run_id: 1, name: 'grad_norm', total_points: 0, points: [] },
      '/events': { items: [], next_cursor: null },
      '/runs/1': makeRun(),
    })
    renderDetail()
    await waitFor(() => expect(screen.getByRole('button', { name: 'grad_norm' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'grad_norm' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('name=grad_norm')),
      ).toBe(true),
    )
  })
})
