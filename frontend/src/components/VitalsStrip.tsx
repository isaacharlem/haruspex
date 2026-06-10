// Cockpit annunciator row: active runs, fleet burn, recovered to date.
// One hairline-bounded strip — no stat boxes.

import { fmtUsd } from '../lib/format'
import type { Ledger, Run } from '../lib/types'

function Vital({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-body text-[11px] uppercase tracking-[0.08em] text-parchment">
        {label}
      </span>
      <span className="font-mono text-base text-bone">{value}</span>
    </div>
  )
}

export function VitalsStrip({ runs, ledger }: { runs: Run[]; ledger: Ledger | undefined }) {
  const live = runs.filter((run) => run.status === 'RUNNING')
  const burn = live.reduce((total, run) => total + run.burn_usd_per_hour, 0)
  const atRisk = live.filter((run) => run.health === 'AT_RISK' || run.health === 'DOOMED').length

  return (
    <div
      className="flex flex-wrap items-center gap-x-10 gap-y-3 border-y px-1 py-3"
      style={{ borderColor: 'var(--bronze-faint)' }}
    >
      <Vital label="Active runs" value={`${live.length}${atRisk ? ` · ${atRisk} at risk` : ''}`} />
      <Vital label="Fleet burn" value={`${fmtUsd(burn)}/hr`} />
      <Vital
        label="Recovered (30d)"
        value={
          ledger
            ? `${fmtUsd(ledger.gross_recovered_usd)} gross · ${fmtUsd(ledger.expected_recovered_usd)} expected`
            : '—'
        }
      />
    </div>
  )
}
