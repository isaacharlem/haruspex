// Ledger: recovered GPU spend, gross and expected, never collapsed.

import { useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { LedgerTable } from '../components/LedgerTable'
import { useLedger } from '../hooks/queries'
import { fmtUsd } from '../lib/format'

const WINDOWS = [7, 30, 90]

export function LedgerPage() {
  const [windowDays, setWindowDays] = useState(30)
  const ledger = useLedger(windowDays)
  const data = ledger.data

  return (
    <div>
      <div className="flex items-end justify-between">
        <h1 className="font-display text-2xl text-bone">Ledger</h1>
        <div className="flex gap-1" role="group" aria-label="window">
          {WINDOWS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setWindowDays(option)}
              className={`border px-2 py-1 font-mono text-xs ${
                windowDays === option ? 'text-bone' : 'text-parchment hover:text-bone'
              }`}
              style={{
                borderColor: windowDays === option ? 'var(--bronze)' : 'var(--bronze-faint)',
              }}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      <div
        className="mt-4 flex flex-wrap gap-x-12 gap-y-3 border-y py-4"
        style={{ borderColor: 'var(--bronze-faint)' }}
      >
        <div>
          <p className="font-body text-[11px] uppercase tracking-[0.08em] text-parchment">
            Gross freed compute
          </p>
          <p className="font-display text-3xl text-bone">{fmtUsd(data?.gross_recovered_usd)}</p>
        </div>
        <div>
          <p className="font-body text-[11px] uppercase tracking-[0.08em] text-parchment">
            Expected value, forecast-weighted
          </p>
          <p className="font-display text-3xl text-bone">{fmtUsd(data?.expected_recovered_usd)}</p>
        </div>
        <p className="max-w-xs self-end font-body text-[11px] text-parchment">
          Gross prices the wall-clock budget a kill freed; expected discounts it by the
          probability the run was going to fail anyway.
        </p>
      </div>

      <div className="mt-6">
        {data && data.rows.length === 0 ? (
          <EmptyState
            title="No kills in this window"
            hint="The ledger fills when a policy (or you) stops a doomed run."
          />
        ) : (
          <LedgerTable rows={data?.rows ?? []} />
        )}
      </div>
    </div>
  )
}
