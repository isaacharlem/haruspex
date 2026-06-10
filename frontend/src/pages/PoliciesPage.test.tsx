import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { mockFetch, renderWithProviders } from '../test/helpers'
import type { Policy } from '../lib/types'
import { PoliciesPage } from './PoliciesPage'

const POLICY: Policy = {
  id: 1,
  name: 'kill-diverging-runs',
  enabled: true,
  version: 2,
  created_at: '2026-06-09T10:00:00Z',
  updated_at: '2026-06-09T11:00:00Z',
  definition: {
    name: 'kill-diverging-runs',
    scope: { tags: ['pretrain'] },
    when: { signal: 'p_diverge', op: '>=', value: 0.85, after_progress: 0.1, sustained_evals: 3 },
    action: { type: 'kill', grace_seconds: 60, min_checkpoint_age_seconds: 120, notify: true },
  },
}

describe('PoliciesPage', () => {
  test('empty state invites the template', async () => {
    mockFetch({ '/policies': [] })
    renderWithProviders(<PoliciesPage />)
    await waitFor(() => expect(screen.getByText('No policies yet')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Start from template' }))
    expect(screen.getByTestId('policy-editor')).toBeInTheDocument()
    expect(screen.getByLabelText(/Name/)).toHaveValue('kill-doomed-after-warmup')
  })

  test('selecting a policy loads it into the editor', async () => {
    mockFetch({ '/policies': [POLICY] })
    renderWithProviders(<PoliciesPage />)
    await waitFor(() => expect(screen.getByText('kill-diverging-runs')).toBeInTheDocument())
    expect(screen.getByText(/v2 · kill · #pretrain/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('kill-diverging-runs'))
    await waitFor(() => expect(screen.getByLabelText(/Name/)).toHaveValue('kill-diverging-runs'))
    expect(screen.getByRole('switch', { name: /enabled/ })).toHaveTextContent('● on')
  })
})
