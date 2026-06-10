// Calibration: the honesty page. Reliability diagrams, Brier, the badge —
// each outcome on its own etched tablet, bounded so the page never sprawls.

import { BrierSparkline } from '../components/BrierSparkline'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { ReliabilityDiagram } from '../components/ReliabilityDiagram'
import { useCalibration } from '../hooks/queries'

const OUTCOME_LABELS: Record<string, string> = {
  hit_target: 'P(hit target)',
  diverge: 'P(diverge)',
}

export function CalibrationPage() {
  const calibration = useCalibration()
  const data = calibration.data

  return (
    <div className="mx-auto max-w-[1000px]">
      <PageHeader
        title="Calibration"
        subtitle={`Forecast probabilities are isotonic-calibrated against your own completed runs. Until ${
          data?.min_samples ?? 30
        } samples exist, probabilities are raw (clipped) and badged as calibrating.`}
      />

      {data && data.outcomes.every((outcome) => outcome.n_samples === 0) ? (
        <div className="mt-8">
          <EmptyState
            title="No completed runs to calibrate against"
            hint="Calibration pairs come from forecasts at 25/50/75% progress on runs that finished. Backfill the demo or let live runs conclude."
          />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {data?.outcomes.map((outcome) => (
            <section
              key={outcome.outcome}
              aria-label={`${outcome.outcome} calibration`}
              className="tablet fade-up p-4"
            >
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="font-display text-lg font-medium text-bone">
                  {OUTCOME_LABELS[outcome.outcome] ?? outcome.outcome}
                </h2>
                {outcome.calibrated ? (
                  <span className="font-mono text-[10px]" style={{ color: 'var(--verdigris)' }}>
                    ● calibrated · n {outcome.n_samples}
                  </span>
                ) : (
                  <span className="font-mono text-[10px]" style={{ color: 'var(--ochre)' }}>
                    ◌ calibrating — {Math.min(outcome.n_samples, data.min_samples)} of{' '}
                    {data.min_samples}
                  </span>
                )}
              </div>
              <div
                className="mt-2 flex flex-wrap items-center justify-between gap-3 border-b pb-3 font-mono text-xs text-parchment"
                style={{ borderColor: 'var(--bronze-ghost, rgba(138,111,63,0.14))' }}
              >
                <span>
                  Brier {outcome.brier_raw?.toFixed(3) ?? '—'}
                  {outcome.brier_calibrated !== null && (
                    <>
                      {' '}
                      → <span className="text-bone">{outcome.brier_calibrated.toFixed(3)}</span>
                    </>
                  )}
                </span>
                <BrierSparkline history={outcome.history} />
              </div>
              <div className="mt-4">
                <ReliabilityDiagram outcome={outcome} />
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
