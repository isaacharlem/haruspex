// Recovered spend, both numbers, never collapsed.

import { fmtRate, fmtTime, fmtUsd } from '../lib/format'
import type { LedgerRow } from '../lib/types'
import { Link } from 'react-router-dom'

export function LedgerTable({ rows }: { rows: LedgerRow[] }) {
  return (
    <table className="w-full font-mono text-xs">
      <thead>
        <tr className="text-left text-parchment">
          <th className="py-2 pr-4 font-normal">run</th>
          <th className="py-2 pr-4 font-normal">killed at</th>
          <th className="py-2 pr-4 font-normal">hardware</th>
          <th className="py-2 pr-4 text-right font-normal">gross freed</th>
          <th className="py-2 text-right font-normal">expected value</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={`${row.run_id}-${row.killed_at}`}
            className="border-t text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
          >
            <td className="py-2 pr-4">
              <Link to={`/runs/${row.run_id}`} className="hover:underline">
                {row.run_name}
              </Link>
            </td>
            <td className="py-2 pr-4 text-parchment">{fmtTime(row.killed_at)}</td>
            <td className="py-2 pr-4 text-parchment">
              {row.gpu_count}×{row.gpu_type} {fmtRate(row.gpu_count * row.gpu_hourly_usd)}
            </td>
            <td className="py-2 pr-4 text-right">{fmtUsd(row.gross_recovered_usd)}</td>
            <td className="py-2 text-right">
              {row.expected_recovered_usd === null ? (
                <span className="text-parchment" title="no forecast existed at kill time">
                  —
                </span>
              ) : (
                fmtUsd(row.expected_recovered_usd)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
