// Reliability diagram: observed rate vs mean forecast against the diagonal,
// bin mass as point size. Honesty rendered. Sized to its container (square,
// capped) so type stays constant at any viewport.

import { fmtProb } from '../lib/format'
import type { OutcomeCalibration } from '../lib/types'
import { useMeasure } from '../hooks/useMeasure'

const PAD = 34
const MAX_SIZE = 360

export function ReliabilityDiagram({ outcome }: { outcome: OutcomeCalibration }) {
  const { ref, width } = useMeasure<HTMLDivElement>(300)
  const size = Math.max(200, Math.min(MAX_SIZE, width))
  const scale = (value: number) => PAD + value * (size - 2 * PAD)
  const flip = (value: number) => size - scale(value)
  const maxCount = Math.max(1, ...outcome.bins.map((bin) => bin.count))
  const occupied = outcome.bins.filter((bin) => bin.count > 0)

  return (
    <div ref={ref} className="flex w-full justify-center">
      <svg
        width={size}
        height={size}
        className="block"
        role="img"
        aria-label={`reliability diagram for ${outcome.outcome}: ${occupied.length} occupied bins over ${outcome.n_samples} samples`}
        style={{ background: 'var(--ink-well)' }}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <g key={tick}>
            <line
              x1={scale(tick)}
              x2={scale(tick)}
              y1={flip(0)}
              y2={flip(1)}
              stroke="var(--bronze-ghost, rgba(138,111,63,0.14))"
              strokeWidth="1"
            />
            <line
              x1={scale(0)}
              x2={scale(1)}
              y1={flip(tick)}
              y2={flip(tick)}
              stroke="var(--bronze-ghost, rgba(138,111,63,0.14))"
              strokeWidth="1"
            />
            <text
              x={scale(tick)}
              y={size - 10}
              fill="var(--parchment)"
              fontSize="9"
              textAnchor="middle"
              fontFamily="IBM Plex Mono, monospace"
            >
              {fmtProb(tick)}
            </text>
            <text
              x={10}
              y={flip(tick) + 3}
              fill="var(--parchment)"
              fontSize="9"
              fontFamily="IBM Plex Mono, monospace"
            >
              {fmtProb(tick)}
            </text>
          </g>
        ))}

        <line
          x1={scale(0)}
          y1={flip(0)}
          x2={scale(1)}
          y2={flip(1)}
          stroke="var(--bronze)"
          strokeWidth="1"
          strokeDasharray="4 4"
        />

        {occupied.map((bin) => (
          <circle
            key={bin.bin_low}
            cx={scale(bin.mean_forecast)}
            cy={flip(bin.observed_rate)}
            r={2 + 6 * Math.sqrt(bin.count / maxCount)}
            fill="var(--verdigris)"
            fillOpacity="0.55"
            stroke="var(--verdigris)"
            strokeWidth="1"
          />
        ))}

        <text
          x={size - PAD}
          y={size - 10}
          fill="var(--parchment)"
          fontSize="8"
          textAnchor="end"
          fontFamily="IBM Plex Mono, monospace"
          opacity="0.7"
        >
          mean forecast →
        </text>
      </svg>
    </div>
  )
}
