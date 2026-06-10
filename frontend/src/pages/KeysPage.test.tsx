import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { setApiKey } from '../lib/api'
import { useKeyStore } from '../state/keyStore'
import { mockFetch, renderWithProviders } from '../test/helpers'
import { KeysPage } from './KeysPage'

const KEY_ROW = {
  id: 1,
  name: 'bootstrap-admin',
  key_prefix: 'hx_abc12',
  scopes: ['admin', 'ingest', 'read'],
  revoked_at: null,
  created_at: '2026-06-09T10:00:00Z',
}

describe('KeysPage', () => {
  beforeEach(() => {
    useKeyStore.setState({ key: 'hx_dashboard-key' })
    setApiKey('hx_dashboard-key')
  })

  test('lists keys and the dashboard connection', async () => {
    mockFetch({ '/admin/keys': [KEY_ROW] })
    renderWithProviders(<KeysPage />)
    await waitFor(() => expect(screen.getByText('bootstrap-admin')).toBeInTheDocument())
    expect(screen.getByText('hx_dashb…')).toBeInTheDocument()
    expect(screen.getByText('hx_abc12…')).toBeInTheDocument()
    expect(screen.getByText('admin, ingest, read')).toBeInTheDocument()
  })

  test('create flow shows the plaintext exactly once', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/admin/keys') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({ ...KEY_ROW, id: 2, name: 'ci-reader', key: 'hx_new-secret-key' }),
          { status: 201 },
        )
      }
      return new Response(JSON.stringify([KEY_ROW]), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<KeysPage />)
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'ci-reader' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }))
    await waitFor(() => expect(screen.getByText('hx_new-secret-key')).toBeInTheDocument())
    expect(screen.getByText(/shown exactly once/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(screen.queryByText('hx_new-secret-key')).not.toBeInTheDocument()
  })

  test('non-admin keys see the scope explanation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { code: 'forbidden', message: 'lacks admin', request_id: 't' },
            }),
            { status: 403 },
          ),
      ),
    )
    renderWithProviders(<KeysPage />)
    await waitFor(() =>
      expect(screen.getByText(/needs a key with the/)).toBeInTheDocument(),
    )
  })
})
