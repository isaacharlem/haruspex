// Typed API client. The dashboard key comes from the key store (localStorage);
// requests go through the vite proxy in dev and nginx in the container.

import type {
  ApiKeyCreated,
  ApiKeyInfo,
  Calibration,
  CopilotStatus,
  DryRunResult,
  Forecast,
  Ledger,
  MetricSeries,
  Page,
  Policy,
  PolicyDefinition,
  PolicyEvent,
  Run,
} from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message)
  }
}

let apiKey = ''

export function setApiKey(key: string): void {
  apiKey = key
}

export function getApiKey(): string {
  return apiKey
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/v1${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    let code = 'http_error'
    let message = `request failed with status ${response.status}`
    let requestId: string | undefined
    try {
      const body = (await response.json()) as {
        error?: { code: string; message: string; request_id: string }
      }
      if (body.error) {
        code = body.error.code
        message = body.error.message
        requestId = body.error.request_id
      }
    } catch {
      // non-JSON error body; keep defaults
    }
    throw new ApiError(response.status, code, message, requestId)
  }
  return (await response.json()) as T
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export const api = {
  listRuns: (filters: { status?: string; tag?: string; text?: string; limit?: number } = {}) =>
    request<Page<Run>>(`/runs${query({ limit: 100, ...filters })}`),
  getRun: (id: number) => request<Run>(`/runs/${id}`),
  getMetrics: (id: number, name: string, maxPoints = 500) =>
    request<MetricSeries>(`/runs/${id}/metrics${query({ name, max_points: maxPoints })}`),
  getForecasts: (id: number, limit = 100) =>
    request<Page<Forecast>>(`/runs/${id}/forecasts${query({ limit })}`),
  killRun: (id: number, graceSeconds: number) =>
    request<Run>(`/runs/${id}/kill`, {
      method: 'POST',
      body: JSON.stringify({ grace_seconds: graceSeconds }),
    }),
  cancelKill: (id: number) =>
    request<Run>(`/runs/${id}/kill`, { method: 'POST', body: JSON.stringify({ cancel: true }) }),

  listPolicies: () => request<Policy[]>('/policies'),
  createPolicy: (definition: PolicyDefinition, enabled = true) =>
    request<Policy>('/policies', { method: 'POST', body: JSON.stringify({ definition, enabled }) }),
  updatePolicy: (id: number, patch: { definition?: PolicyDefinition; enabled?: boolean }) =>
    request<Policy>(`/policies/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  dryRunPolicy: (definition: PolicyDefinition) =>
    request<DryRunResult>('/policies/dry-run', {
      method: 'POST',
      body: JSON.stringify({ definition }),
    }),

  listEvents: (filters: { run_id?: number; limit?: number } = {}) =>
    request<Page<PolicyEvent>>(`/events${query({ limit: 50, ...filters })}`),
  getLedger: (windowDays: number) => request<Ledger>(`/ledger${query({ window_days: windowDays })}`),
  getCalibration: () => request<Calibration>('/calibration'),

  listKeys: () => request<ApiKeyInfo[]>('/admin/keys'),
  createKey: (name: string, scopes: string[]) =>
    request<ApiKeyCreated>('/admin/keys', { method: 'POST', body: JSON.stringify({ name, scopes }) }),
  revokeKey: (id: number) => request<ApiKeyInfo>(`/admin/keys/${id}/revoke`, { method: 'POST' }),

  copilotStatus: () => request<CopilotStatus>('/copilot/status'),
}
