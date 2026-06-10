// Fleet: is anything dying, and what is it costing me?

import { useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { RunCard } from '../components/RunCard'
import { VitalsStrip } from '../components/VitalsStrip'
import { useLedger, useRuns } from '../hooks/queries'
import { bySeverity } from '../lib/status'

const STATUS_FILTERS = ['ALL', 'RUNNING', 'COMPLETED', 'DIVERGED', 'KILLED', 'LOST']

export function FleetPage() {
  const [status, setStatus] = useState('ALL')
  const [text, setText] = useState('')
  const runsQuery = useRuns({
    ...(status !== 'ALL' ? { status } : {}),
    ...(text ? { text } : {}),
  })
  const ledger = useLedger(30)

  const runs = [...(runsQuery.data?.items ?? [])].sort(bySeverity)
  const live = runs.filter((run) => run.status === 'RUNNING')
  const finished = runs.filter((run) => run.status !== 'RUNNING')

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-2xl text-bone">Fleet</h1>
        <div className="flex gap-2">
          <label className="sr-only" htmlFor="fleet-status">
            Filter by status
          </label>
          <select
            id="fleet-status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="border bg-ink-well px-2 py-1 font-mono text-xs text-parchment"
            style={{ borderColor: 'var(--bronze-faint)' }}
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor="fleet-search">
            Search runs by name
          </label>
          <input
            id="fleet-search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="w-44 border bg-ink-well px-2 py-1 font-mono text-xs text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
            aria-label="search runs by name"
          />
        </div>
      </div>

      <div className="mt-4">
        <VitalsStrip runs={runsQuery.data?.items ?? []} ledger={ledger.data} />
      </div>

      {runsQuery.isLoading ? (
        <p className="mt-8 font-mono text-xs text-parchment">consulting the entrails…</p>
      ) : runs.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No runs yet"
            hint="Instrument a training loop with the haruspex SDK, or seed the demo: haruspex-simulate backfill --runs 40 --fast"
          />
        </div>
      ) : (
        <>
          {live.length > 0 && (
            <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {live.map((run) => (
                <RunCard key={run.id} run={run} />
              ))}
            </div>
          )}
          {finished.length > 0 && (
            <>
              <h2 className="mt-8 font-body text-[11px] font-semibold uppercase tracking-[0.08em] text-parchment">
                Concluded
              </h2>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {finished.map((run) => (
                  <RunCard key={run.id} run={run} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
