// Calibration: the honesty page. Reliability diagrams, Brier, the badge.

import { BrierSparkline } from '../components/BrierSparkline'
import { EmptyState } from '../components/EmptyState'
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
    <div>
      <h1 className="font-display text-2xl text-bone">Calibration</h1>
      <p className="mt-1 max-w-xl font-body text-xs text-parchment">
        Forecast probabilities are isotonic-calibrated against your own completed runs. Until{' '}
        {data?.min_samples ?? 30} samples exist, probabilities are raw (clipped) and badged as
        calibrating.
      </p>

      {data && data.outcomes.every((outcome) => outcome.n_samples === 0) ? (
        <div className="mt-8">
          <EmptyState
            title="No completed runs to calibrate against"
            hint="Calibration pairs come from forecasts at 25/50/75% progress on runs that finished. Backfill the demo or let live runs conclude."
          />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-2">
          {data?.outcomes.map((outcome) => (
            <section key={outcome.outcome} aria-label={`${outcome.outcome} calibration`}>
              <div className="flex items-baseline justify-between">
                <h2 className="font-body text-sm font-semibold text-bone">
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
              <div className="mt-2 flex flex-wrap items-center gap-4 font-mono text-xs text-parchment">
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
              <div className="mt-3">
                <ReliabilityDiagram outcome={outcome} />
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
