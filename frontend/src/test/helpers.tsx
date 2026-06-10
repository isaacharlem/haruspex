import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import type { Forecast, Run } from '../lib/types'

export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

export function makeForecast(overrides: Partial<Forecast> = {}): Forecast {
  return {
    id: 1,
    run_id: 1,
    as_of_progress: 0.4,
    p_hit_target: 0.72,
    p_diverge: 0.08,
    p_plateau: 0.2,
    eta_quantiles: { q10: 2.7, q25: 2.75, q50: 2.8, q75: 2.86, q90: 2.93 },
    components: {
      curve: { weights: { pow3: 0.8, exp3: 0.2 }, p_raw: 0.7 },
      divergence: { features: { z_dgrad: 0.4, jump_now: 0.02 }, p_raw: 0.1 },
    },
    calibrated: false,
    created_at: '2026-06-09T12:00:00Z',
    ...overrides,
  }
}

export function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    id: 1,
    name: 'gpt2-small-bf16',
    tags: ['pretrain'],
    framework: 'pytorch',
    status: 'RUNNING',
    health: 'HEALTHY',
    target_metric: 'loss',
    target_value: 2.9,
    direction: 'min',
    budget_steps: 10_000,
    budget_wallclock_s: 14_400,
    gpu_type: 'H100',
    gpu_count: 8,
    gpu_hourly_usd: 2.5,
    burn_usd_per_hour: 20,
    started_at: '2026-06-09T10:00:00Z',
    ended_at: null,
    last_heartbeat_at: '2026-06-09T12:00:00Z',
    last_checkpoint_at: '2026-06-09T11:58:00Z',
    current_step: 4100,
    progress: 0.41,
    directive: 'NONE',
    directive_issued_at: null,
    directive_grace_s: null,
    kill_acked_at: null,
    final_value: null,
    created_at: '2026-06-09T10:00:00Z',
    latest_forecast: makeForecast(),
    ...overrides,
  }
}

type RouteMap = Record<string, unknown>

export function mockFetch(routes: RouteMap): ReturnType<typeof vi.fn> {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    for (const [prefix, body] of Object.entries(routes)) {
      if (url.includes(prefix)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
    }
    return new Response(
      JSON.stringify({ error: { code: 'not_found', message: url, request_id: 't' } }),
      { status: 404 },
    )
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
