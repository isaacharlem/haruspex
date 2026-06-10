// Run detail: the instrument, the prognosis numerals, the audit trail.
// The chart claims a bounded, viewport-aware band (no dead space below);
// the prognosis reads like a gauge plate, each probability with its meter.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { EventTimeline } from '../components/EventTimeline'
import { ForecastComponentsPanel } from '../components/ForecastComponentsPanel'
import { KillConfirmDialog } from '../components/KillConfirmDialog'
import { SectionRule } from '../components/PageHeader'
import { StatusSigil } from '../components/StatusSigil'
import { TraceCanvas } from '../components/TraceCanvas'
import { useEvents, useMetrics, useRun } from '../hooks/queries'
import { api, ApiError } from '../lib/api'
import { fmtAge, fmtMetric, fmtProb, fmtRate, fmtStep } from '../lib/format'
import { runStatusVisual } from '../lib/status'
import { useUiStore } from '../state/uiStore'

const METRIC_TABS = ['target', 'grad_norm', 'lr'] as const

const PROGNOSIS_COLOR: Record<string, string> = {
  'P(hit target)': 'var(--verdigris)',
  'P(diverge)': 'var(--oxblood)',
  'P(plateau)': 'var(--ochre)',
}

export function RunDetailPage() {
  const { id } = useParams()
  const runId = Number(id)
  const runQuery = useRun(runId)
  const [tab, setTab] = useState<(typeof METRIC_TABS)[number]>('target')
  const [killOpen, setKillOpen] = useState(false)
  const pushToast = useUiStore((state) => state.pushToast)
  const queryClient = useQueryClient()

  const run = runQuery.data
  const metricName = tab === 'target' ? (run?.target_metric ?? 'loss') : tab
  const metrics = useMetrics(runId, metricName)
  const events = useEvents(runId)

  const kill = useMutation({
    mutationFn: (graceSeconds: number) => api.killRun(runId, graceSeconds),
    onSuccess: () => {
      setKillOpen(false)
      pushToast('Kill directed. The trainer stops on its next heartbeat.', 'kill')
      void queryClient.invalidateQueries({ queryKey: ['run', runId] })
    },
    onError: (error) =>
      pushToast(error instanceof ApiError ? error.message : 'Kill failed', 'warn'),
  })
  const cancelKill = useMutation({
    mutationFn: () => api.cancelKill(runId),
    onSuccess: () => {
      pushToast('Kill overridden. The run keeps going.', 'info')
      void queryClient.invalidateQueries({ queryKey: ['run', runId] })
    },
    onError: (error) =>
      pushToast(error instanceof ApiError ? error.message : 'Override failed', 'warn'),
  })

  if (runQuery.isLoading) {
    return <p className="augur-shimmer font-mono text-xs text-parchment">reading the run…</p>
  }
  if (!run) {
    return (
      <p className="font-body text-sm text-parchment">
        This run does not exist. It may have been registered against another database.
      </p>
    )
  }

  const visual = runStatusVisual(run)
  const forecast = run.latest_forecast
  const killable = run.status === 'RUNNING' && run.directive === 'NONE'
  const overridable = run.directive === 'KILL' && run.kill_acked_at === null

  return (
    <div>
      <header>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="max-w-full truncate font-display text-[26px] font-medium tracking-tight text-bone">
            {run.name}
          </h1>
          <StatusSigil visual={visual} />
          {run.tags.map((tag) => (
            <span key={tag} className="font-mono text-[10px] text-bronze">
              #{tag}
            </span>
          ))}
          <span className="font-mono text-xs text-parchment">
            {run.gpu_count}×{run.gpu_type} · {fmtRate(run.burn_usd_per_hour)} · step{' '}
            {fmtStep(run.current_step)}/{fmtStep(run.budget_steps)} · heartbeat{' '}
            {fmtAge(run.last_heartbeat_at)}
          </span>
          <span className="ml-auto flex gap-2">
            {overridable && (
              <button
                type="button"
                onClick={() => cancelKill.mutate()}
                className="border px-3 py-1.5 font-body text-xs transition-colors hover:bg-ink-well"
                style={{ borderColor: 'var(--verdigris)', color: 'var(--verdigris)' }}
              >
                Override kill
              </button>
            )}
            {killable && (
              <button
                type="button"
                onClick={() => setKillOpen(true)}
                className="border px-3 py-1.5 font-body text-xs text-parchment transition-colors hover:border-current hover:text-[var(--oxblood)]"
                style={{ borderColor: 'var(--bronze-faint)' }}
                data-testid="kill-button"
              >
                Kill run
              </button>
            )}
          </span>
        </div>
        <div className="etched-rule mt-3" aria-hidden="true" />
      </header>

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-label="metric trace" className="min-w-0">
          <div className="flex gap-1">
            {METRIC_TABS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setTab(option)}
                className={`border-b-2 px-3 py-1 font-mono text-xs transition-colors ${
                  tab === option ? 'text-bone' : 'text-parchment hover:text-bone'
                }`}
                style={{ borderColor: tab === option ? 'var(--bronze)' : 'transparent' }}
              >
                {option === 'target' ? run.target_metric : option}
              </button>
            ))}
          </div>
          <div
            className="mt-2 h-[clamp(320px,52vh,540px)] border"
            style={{ borderColor: 'var(--bronze-faint)' }}
          >
            <TraceCanvas
              run={run}
              points={metrics.data?.points ?? []}
              forecast={tab === 'target' ? forecast : null}
              showTarget={tab === 'target'}
            />
          </div>
          <p className="mt-1 text-right font-mono text-[10px] text-parchment">
            {metrics.data
              ? `${metrics.data.points.length} of ${metrics.data.total_points} points (LTTB)`
              : ''}
          </p>
        </section>

        <aside className="min-w-0 space-y-6">
          <section aria-label="prognosis" className="tablet space-y-4 p-4">
            {(
              [
                ['P(hit target)', forecast?.p_hit_target],
                ['P(diverge)', forecast?.p_diverge],
                ['P(plateau)', forecast?.p_plateau],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-xs text-parchment">{label}</span>
                  <span className="font-display text-4xl font-medium text-bone">
                    {fmtProb(value)}
                  </span>
                </div>
                <div
                  className="mt-1.5 h-px w-full overflow-visible"
                  style={{ background: 'var(--bronze-ghost, rgba(138,111,63,0.14))' }}
                  aria-hidden="true"
                >
                  <div
                    className="h-[3px] -translate-y-px transition-[width] duration-500"
                    style={{
                      width: `${Math.round((value ?? 0) * 100)}%`,
                      background: PROGNOSIS_COLOR[label],
                      opacity: 0.85,
                    }}
                  />
                </div>
              </div>
            ))}
            {forecast && (
              <p className="font-mono text-[10px] leading-relaxed text-parchment">
                median final {run.target_metric} {fmtMetric(forecast.eta_quantiles.q50)} · as of{' '}
                {Math.round(forecast.as_of_progress * 100)}% progress
              </p>
            )}
          </section>

          {forecast && (
            <div className="tablet p-4">
              <ForecastComponentsPanel forecast={forecast} />
            </div>
          )}

          <section aria-label="events">
            <SectionRule>Events</SectionRule>
            <div className="mt-2.5">
              <EventTimeline events={events.data?.items ?? []} />
            </div>
          </section>
        </aside>
      </div>

      {killOpen && (
        <KillConfirmDialog
          run={run}
          onConfirm={(grace) => kill.mutate(grace)}
          onClose={() => setKillOpen(false)}
        />
      )}
    </div>
  )
}
