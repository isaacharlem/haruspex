import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { DryRunResult } from '../lib/types'
import { useKeyStore } from '../state/keyStore'
import { useUiStore } from '../state/uiStore'
import { AppShell } from './AppShell'
import { DryRunDrawer } from './DryRunDrawer'
import { Toasts } from './Toasts'

describe('Toasts', () => {
  beforeEach(() => {
    useUiStore.setState({ toasts: [] })
  })

  test('pushToast renders and click dismisses', () => {
    render(<Toasts />)
    act(() => useUiStore.getState().pushToast('Run killed', 'kill'))
    expect(screen.getByText('Run killed')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('toast'))
    expect(screen.queryByText('Run killed')).not.toBeInTheDocument()
  })
})

describe('DryRunDrawer', () => {
  const result: DryRunResult = {
    would_have_fired: [
      {
        run_id: 7,
        run_name: 'doomed-history',
        at_progress: 0.4,
        signal_value: 0.93,
        est_gross_usd: 120,
        est_expected_usd: 110,
      },
    ],
    est_gross_usd: 120,
    est_expected_usd: 110,
    runs_scanned: 12,
    assumptions: ['checkpoint guard assumed satisfied at fire time'],
  }

  test('shows fires, totals, and assumptions; Esc closes', () => {
    const onClose = vi.fn()
    render(<DryRunDrawer result={result} onClose={onClose} />)
    expect(screen.getByText('doomed-history')).toBeInTheDocument()
    expect(screen.getByText('40% progress')).toBeInTheDocument()
    expect(screen.getByText(/1 of 12 historical runs/)).toBeInTheDocument()
    expect(screen.getByText(/checkpoint guard assumed/)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  test('empty result explains how to make it fire', () => {
    render(
      <DryRunDrawer
        result={{ ...result, would_have_fired: [], est_gross_usd: 0, est_expected_usd: 0 }}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText(/never fires on your history/)).toBeInTheDocument()
  })
})

describe('AppShell', () => {
  test('renders navigation and the outlet', () => {
    useKeyStore.setState({ key: '' }) // no key: the SSE effect stays idle
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<p>fleet content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByRole('navigation', { name: 'primary' })).toBeInTheDocument()
    expect(screen.getByText('Fleet')).toBeInTheDocument()
    expect(screen.getByText('Calibration')).toBeInTheDocument()
    expect(screen.getByText('fleet content')).toBeInTheDocument()
  })
})
