// Ledger: recovered GPU spend, gross and expected, never collapsed.

import { useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { LedgerTable } from '../components/LedgerTable'
import { PageHeader } from '../components/PageHeader'
import { useLedger } from '../hooks/queries'
import { fmtUsd } from '../lib/format'

const WINDOWS = [7, 30, 90]

export function LedgerPage() {
  const [windowDays, setWindowDays] = useState(30)
  const ledger = useLedger(windowDays)
  const data = ledger.data

  return (
    <div className="mx-auto max-w-[1100px]">
      <PageHeader
        title="Ledger"
        actions={
          <div className="flex gap-1" role="group" aria-label="window">
            {WINDOWS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setWindowDays(option)}
                className={`border px-2.5 py-1 font-mono text-xs transition-colors ${
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
        }
      />

      <div className="tablet mt-4 flex flex-wrap items-stretch">
        <div
          className="border-r px-5 py-4 sm:px-7"
          style={{ borderColor: 'var(--bronze-ghost, rgba(138,111,63,0.14))' }}
        >
          <p className="font-body text-[10px] tracking-[0.14em] text-parchment uppercase">
            Gross freed compute
          </p>
          <p className="mt-1 font-display text-3xl font-medium text-bone">
            {fmtUsd(data?.gross_recovered_usd)}
          </p>
        </div>
        <div
          className="border-r px-5 py-4 sm:px-7"
          style={{ borderColor: 'var(--bronze-ghost, rgba(138,111,63,0.14))' }}
        >
          <p className="font-body text-[10px] tracking-[0.14em] text-parchment uppercase">
            Expected value, forecast-weighted
          </p>
          <p className="mt-1 font-display text-3xl font-medium text-bone">
            {fmtUsd(data?.expected_recovered_usd)}
          </p>
        </div>
        <p className="max-w-xs self-center px-5 py-4 font-body text-[11px] leading-relaxed text-parchment sm:px-7">
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
