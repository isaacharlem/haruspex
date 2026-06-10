import { beforeEach, describe, expect, test, vi } from 'vitest'
import { api, ApiError, setApiKey } from './api'

describe('api client', () => {
  beforeEach(() => {
    setApiKey('hx_test')
  })

  test('sends the bearer header and parses JSON', async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const page = await api.listRuns({ status: 'RUNNING' })
    expect(page.items).toEqual([])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/v1/runs?')
    expect(url).toContain('status=RUNNING')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer hx_test')
  })

  test('error envelopes become ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { code: 'rate_limited', message: 'slow down', request_id: 'r1' },
            }),
            { status: 429 },
          ),
      ),
    )
    const error = await api.getRun(1).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('rate_limited')
    expect((error as ApiError).status).toBe(429)
    expect((error as ApiError).requestId).toBe('r1')
  })

  test('non-JSON errors degrade gracefully', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 502 })))
    const error = await api.getLedger(30).catch((caught: unknown) => caught)
    expect((error as ApiError).code).toBe('http_error')
  })

  test('mutations serialize JSON bodies', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.killRun(7, 60)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/v1/runs/7/kill')
    expect(JSON.parse(String(init.body))).toEqual({ grace_seconds: 60 })
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })
})
