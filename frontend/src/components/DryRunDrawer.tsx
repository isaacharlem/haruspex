// Bottom drawer: what this rule would have done to your history, in dollars.

import { useEffect } from 'react'
import { fmtPercent, fmtProb, fmtUsd } from '../lib/format'
import type { DryRunResult } from '../lib/types'

export function DryRunDrawer({ result, onClose }: { result: DryRunResult; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-30 max-h-[60vh] overflow-y-auto border-t bg-ink-raised p-4 shadow-2xl"
      style={{ borderColor: 'var(--bronze)' }}
      role="dialog"
      aria-label="dry run results"
      data-testid="dry-run-drawer"
    >
      <div className="mx-auto max-w-4xl">
        <div className="flex items-baseline justify-between">
          <h3 className="font-display text-lg text-bone">Would have fired</h3>
          <button
            type="button"
            onClick={onClose}
            className="border px-2 py-1 font-mono text-[10px] text-parchment hover:text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
          >
            Esc to close
          </button>
        </div>
        <p className="mt-1 font-mono text-xs text-parchment">
          {result.would_have_fired.length} of {result.runs_scanned} historical runs ·{' '}
          <span className="text-bone">{fmtUsd(result.est_gross_usd)}</span> gross ·{' '}
          <span className="text-bone">{fmtUsd(result.est_expected_usd)}</span> expected
        </p>

        {result.would_have_fired.length === 0 ? (
          <p className="mt-4 font-body text-xs text-parchment">
            This rule never fires on your history. Loosen the threshold or lower after-progress
            to see it act.
          </p>
        ) : (
          <table className="mt-3 w-full font-mono text-[11px]">
            <thead>
              <tr className="text-left text-parchment">
                <th className="py-1 pr-4 font-normal">run</th>
                <th className="py-1 pr-4 font-normal">fires at</th>
                <th className="py-1 pr-4 font-normal">signal</th>
                <th className="py-1 pr-4 text-right font-normal">gross</th>
                <th className="py-1 text-right font-normal">expected</th>
              </tr>
            </thead>
            <tbody>
              {result.would_have_fired.map((fire) => (
                <tr
                  key={`${fire.run_id}-${fire.at_progress}`}
                  className="border-t text-bone"
                  style={{ borderColor: 'var(--bronze-faint)' }}
                >
                  <td className="py-1 pr-4">{fire.run_name}</td>
                  <td className="py-1 pr-4">{fmtPercent(fire.at_progress)} progress</td>
                  <td className="py-1 pr-4">{fmtProb(fire.signal_value)}</td>
                  <td className="py-1 pr-4 text-right">{fmtUsd(fire.est_gross_usd)}</td>
                  <td className="py-1 text-right">{fmtUsd(fire.est_expected_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <p className="mt-3 font-body text-[10px] text-parchment">
          Assumptions: {result.assumptions.join('; ')}.
        </p>
      </div>
    </div>
  )
}
