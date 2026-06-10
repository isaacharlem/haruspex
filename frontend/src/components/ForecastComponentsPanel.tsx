// How the augury was read: curve family weights, divergence features,
// calibration badge. Distinguishes "the forecast said" from raw guts.

import { fmtMetric, fmtProb } from '../lib/format'
import type { Forecast } from '../lib/types'

interface CurveComponents {
  weights?: Record<string, number>
  p_raw?: number
}

interface DivergenceComponents {
  features?: Record<string, number>
  p_raw?: number
}

const FEATURE_LABELS: Record<string, string> = {
  z_dgrad: 'z Δgrad',
  jump_now: 'loss elevation',
  rise_frac: 'rise fraction',
  nonfinite: 'NaN/Inf',
  lr_grad: 'lr × grad',
}

export function ForecastComponentsPanel({ forecast }: { forecast: Forecast }) {
  const curve = (forecast.components.curve ?? {}) as CurveComponents
  const divergence = (forecast.components.divergence ?? {}) as DivergenceComponents
  const weights = Object.entries(curve.weights ?? {}).sort((a, b) => b[1] - a[1])
  const features = Object.entries(divergence.features ?? {})
  const insufficient = Boolean(forecast.components.insufficient_data)

  return (
    <section aria-label="forecast components">
      <h3 className="font-body text-[11px] font-semibold uppercase tracking-[0.08em] text-parchment">
        Forecast components
      </h3>

      {insufficient ? (
        <p className="mt-2 font-body text-xs text-parchment">
          Too few points to fit curves yet — probabilities are priors.
        </p>
      ) : (
        <>
          <div className="mt-2 space-y-1.5">
            {weights.map(([family, weight]) => (
              <div key={family} className="flex items-center gap-2">
                <span className="w-20 font-mono text-[11px] text-parchment">{family}</span>
                <span
                  className="h-1.5"
                  style={{
                    width: `${Math.max(2, weight * 140)}px`,
                    background: 'var(--bronze)',
                    opacity: 0.4 + weight * 0.6,
                  }}
                  aria-hidden="true"
                />
                <span className="font-mono text-[11px] text-bone">{fmtProb(weight)}</span>
              </div>
            ))}
          </div>

          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
            {features.map(([name, value]) => (
              <div key={name} className="flex justify-between font-mono text-[11px]">
                <span className="text-parchment">{FEATURE_LABELS[name] ?? name}</span>
                <span className="text-bone">{fmtMetric(value)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <div
        className="mt-3 border-t pt-2 font-mono text-[11px]"
        style={{ borderColor: 'var(--bronze-faint)' }}
      >
        {forecast.calibrated ? (
          <span style={{ color: 'var(--verdigris)' }}>● calibrated probabilities</span>
        ) : (
          <span style={{ color: 'var(--ochre)' }}>◌ calibrating — raw, clipped to [0.05, 0.95]</span>
        )}
        {curve.p_raw !== undefined && (
          <span className="ml-3 text-parchment">raw P(hit) {fmtProb(curve.p_raw)}</span>
        )}
      </div>
    </section>
  )
}
