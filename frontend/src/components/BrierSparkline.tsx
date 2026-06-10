// Brier score across calibration refits: lower is better.

import type { CalibrationFitPoint } from '../lib/types'

export function BrierSparkline({ history }: { history: CalibrationFitPoint[] }) {
  const points = history.filter((point) => point.brier_after !== null)
  if (points.length < 2) {
    return <span className="font-mono text-[10px] text-parchment">history grows with each refit</span>
  }
  const width = 120
  const height = 24
  const values = points.map((point) => point.brier_after as number)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * (width - 4) + 2
      const y = height - 4 - ((value - min) / span) * (height - 8)
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label={`Brier score across ${values.length} refits, latest ${values.at(-1)?.toFixed(3)}`}
    >
      <path d={path} fill="none" stroke="var(--verdigris)" strokeWidth="1.2" />
    </svg>
  )
}
