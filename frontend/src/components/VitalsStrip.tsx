// Cockpit annunciator plaque: active runs, fleet burn, recovered to date.
// One etched strip with hairline dividers and display numerals.

import { fmtUsd } from '../lib/format'
import type { Ledger, Run } from '../lib/types'

function Vital({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div
      className="flex min-w-0 flex-col gap-1 border-r px-5 py-3 last:border-r-0 sm:px-7"
      style={{ borderColor: 'var(--bronze-ghost, rgba(138,111,63,0.14))' }}
    >
      <span className="font-body text-[10px] tracking-[0.14em] whitespace-nowrap text-parchment uppercase">
        {label}
      </span>
      <span
        className="truncate font-display text-xl font-medium text-bone"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </span>
    </div>
  )
}

export function VitalsStrip({ runs, ledger }: { runs: Run[]; ledger: Ledger | undefined }) {
  const live = runs.filter((run) => run.status === 'RUNNING')
  const burn = live.reduce((total, run) => total + run.burn_usd_per_hour, 0)
  const atRisk = live.filter((run) => run.health === 'AT_RISK' || run.health === 'DOOMED').length

  return (
    <div className="tablet flex flex-wrap items-stretch">
      <Vital
        label="Active runs"
        value={`${live.length}${atRisk ? ` · ${atRisk} at risk` : ''}`}
        accent={atRisk ? 'var(--ochre)' : undefined}
      />
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
