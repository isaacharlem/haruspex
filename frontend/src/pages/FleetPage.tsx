// Fleet: is anything dying, and what is it costing me?

import { useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { PageHeader, SectionRule } from '../components/PageHeader'
import { RunCard } from '../components/RunCard'
import { VitalsStrip } from '../components/VitalsStrip'
import { useLedger, useRuns } from '../hooks/queries'
import { bySeverity } from '../lib/status'

const STATUS_FILTERS = ['ALL', 'RUNNING', 'COMPLETED', 'DIVERGED', 'KILLED', 'LOST']

/* Cards never balloon: the grid mints as many 300–380px columns as fit. */
const CARD_GRID =
  'grid grid-cols-1 gap-3.5 sm:[grid-template-columns:repeat(auto-fill,minmax(300px,1fr))] [&>*]:max-w-[460px]'

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
      <PageHeader
        title="Fleet"
        actions={
          <>
            <label className="sr-only" htmlFor="fleet-status">
              Filter by status
            </label>
            <select
              id="fleet-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="border bg-ink-well px-2 py-1.5 font-mono text-xs text-parchment transition-colors hover:border-bronze"
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
              className="w-44 border bg-ink-well px-2 py-1.5 font-mono text-xs text-bone transition-colors hover:border-bronze"
              style={{ borderColor: 'var(--bronze-faint)' }}
              aria-label="search runs by name"
            />
          </>
        }
      />

      <div className="mt-4">
        <VitalsStrip runs={runsQuery.data?.items ?? []} ledger={ledger.data} />
      </div>

      {runsQuery.isLoading ? (
        <p className="augur-shimmer mt-8 font-mono text-xs text-parchment">
          consulting the entrails…
        </p>
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
            <section aria-label="live runs" className="fade-up mt-7">
              <SectionRule>Live</SectionRule>
              <div className={`mt-3 ${CARD_GRID}`}>
                {live.map((run) => (
                  <RunCard key={run.id} run={run} />
                ))}
              </div>
            </section>
          )}
          {finished.length > 0 && (
            <section aria-label="concluded runs" className="fade-up mt-8">
              <SectionRule>Concluded</SectionRule>
              <div className={`mt-3 ${CARD_GRID}`}>
                {finished.map((run) => (
                  <RunCard key={run.id} run={run} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
