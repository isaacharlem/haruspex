// One run at a glance: name, sigil, mini trace + fan, prognosis, burn.

import { Link } from 'react-router-dom'
import { fmtProb, fmtRate, fmtStep } from '../lib/format'
import { runStatusVisual } from '../lib/status'
import type { Run } from '../lib/types'
import { StatusSigil } from './StatusSigil'
import { TraceCanvas } from './TraceCanvas'
import { useMetrics } from '../hooks/queries'

export function RunCard({ run }: { run: Run }) {
  const visual = runStatusVisual(run)
  const metrics = useMetrics(run.id, run.target_metric)
  const forecast = run.latest_forecast
  const terminal = run.status !== 'RUNNING'
  const headline =
    forecast === null
      ? ['P(hit target)', '—']
      : run.health === 'DOOMED' || (forecast.p_diverge > forecast.p_hit_target && !terminal)
        ? ['P(diverge)', fmtProb(forecast.p_diverge)]
        : ['P(hit target)', fmtProb(forecast.p_hit_target)]

  return (
    <Link
      to={`/runs/${run.id}`}
      className={`block border bg-ink-raised p-3 transition-colors duration-300 hover:border-bone ${
        terminal ? 'opacity-60' : ''
      }`}
      style={{ borderColor: 'var(--bronze-faint)' }}
      data-testid="run-card"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-body text-sm font-semibold text-bone">{run.name}</span>
        <StatusSigil visual={visual} />
      </div>

      <div className="mt-2 h-16">
        <TraceCanvas
          run={run}
          points={metrics.data?.points ?? []}
          forecast={forecast}
          showTarget={false}
          compact
        />
      </div>

      <div className="mt-2 flex items-baseline justify-between font-mono text-xs">
        <span className="text-parchment">
          {headline[0]} <span className="text-bone">{headline[1]}</span>
          {forecast && !forecast.calibrated && (
            <span className="ml-1 text-[9px] uppercase tracking-wide text-bronze">~cal</span>
          )}
        </span>
        <span className="text-parchment">
          {fmtStep(run.current_step)}/{fmtStep(run.budget_steps)}
        </span>
      </div>
      <div className="mt-1 flex items-baseline justify-between font-mono text-[11px] text-parchment">
        <span>
          {run.gpu_count}×{run.gpu_type}
        </span>
        <span>{run.status === 'RUNNING' ? fmtRate(run.burn_usd_per_hour) : run.status.toLowerCase()}</span>
      </div>
    </Link>
  )
}
