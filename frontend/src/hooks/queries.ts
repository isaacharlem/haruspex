// TanStack Query wrappers. No polling anywhere: the SSE hook invalidates.

import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

export function useRuns(filters: { status?: string; tag?: string; text?: string } = {}) {
  return useQuery({
    queryKey: ['runs', filters],
    queryFn: () => api.listRuns(filters),
  })
}

export function useRun(id: number) {
  return useQuery({ queryKey: ['run', id], queryFn: () => api.getRun(id) })
}

export function useMetrics(id: number, name: string) {
  return useQuery({
    queryKey: ['metrics', id, name],
    queryFn: () => api.getMetrics(id, name),
  })
}

export function useForecasts(id: number) {
  return useQuery({ queryKey: ['forecasts', id], queryFn: () => api.getForecasts(id) })
}

export function usePolicies() {
  return useQuery({ queryKey: ['policies'], queryFn: api.listPolicies })
}

export function useEvents(runId?: number) {
  return useQuery({
    queryKey: ['events', runId ?? 'all'],
    queryFn: () => api.listEvents(runId ? { run_id: runId } : {}),
  })
}

export function useLedger(windowDays: number) {
  return useQuery({
    queryKey: ['ledger', windowDays],
    queryFn: () => api.getLedger(windowDays),
  })
}

export function useCalibration() {
  return useQuery({ queryKey: ['calibration'], queryFn: api.getCalibration })
}

export function useApiKeys() {
  return useQuery({ queryKey: ['keys'], queryFn: api.listKeys })
}

export function useCopilotStatus() {
  return useQuery({ queryKey: ['copilot-status'], queryFn: api.copilotStatus })
}
