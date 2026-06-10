// The instrument: live metric trace with etched axes, target hairline,
// comet head, and the prognosis fan toward budget-end. Renders at true pixel
// size (measured, not viewBox-stretched) so type and stroke weights hold at
// any viewport; the y-domain is quantile-clipped so a single warmup outlier
// can't flatten the whole story.

import * as d3 from 'd3'
import { useId, useMemo } from 'react'
import { fmtMetric, fmtProb, fmtStep } from '../lib/format'
import type { Forecast, MetricPoint, Run } from '../lib/types'
import { runStatusVisual } from '../lib/status'
import { useMeasure } from '../hooks/useMeasure'
import { PrognosisFan, type FanGeometry } from './PrognosisFan'

interface TraceCanvasProps {
  run: Run
  points: MetricPoint[]
  forecast: Forecast | null
  showTarget: boolean
  compact?: boolean
}

const MARGIN = { top: 14, right: 52, bottom: 26, left: 12 }
const COMPACT_MARGIN = { top: 4, right: 2, bottom: 4, left: 2 }

/* Fence the domain so warmup transients don't crush the curve (LTTB keeps
   extremes, so plain quantile clips aren't enough — use an IQR fence around
   the median). Never clip away the data that matters: the recent trace, the
   target, and the fan ride in via mustInclude and re-widen the domain. */
function robustDomain(values: number[], mustInclude: number[]): [number, number] {
  if (values.length === 0 && mustInclude.length === 0) return [0, 1]
  const sorted = [...values].sort(d3.ascending)
  let lo = Infinity
  let hi = -Infinity
  if (sorted.length) {
    lo = d3.quantileSorted(sorted, 0.02) ?? sorted[0]
    const p50 = d3.quantileSorted(sorted, 0.5) ?? sorted[0]
    const p90 = d3.quantileSorted(sorted, 0.9) ?? sorted.at(-1)!
    const iqr =
      (d3.quantileSorted(sorted, 0.75) ?? p50) - (d3.quantileSorted(sorted, 0.25) ?? p50)
    const spread = Math.max(iqr, (p90 - p50) / 2, Math.abs(p50) * 1e-3, 1e-9)
    hi = Math.max(p90, p50 + 8 * spread)
  }
  for (const value of mustInclude) {
    if (Number.isFinite(value)) {
      lo = Math.min(lo, value)
      hi = Math.max(hi, value)
    }
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1]
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.08
  return [lo - pad, hi + pad]
}

export function TraceCanvas({ run, points, forecast, showTarget, compact = false }: TraceCanvasProps) {
  const gradientId = useId().replace(/:/g, '')
  const { ref, width, height } = useMeasure<HTMLDivElement>(
    compact ? 280 : 720,
    compact ? 64 : 380,
  )
  const margin = compact ? COMPACT_MARGIN : MARGIN
  const visual = runStatusVisual(run)
  const isLive = run.status === 'RUNNING'

  const { xScale, yScale, linePath, areaPath, head, fanGeometry } = useMemo(() => {
    const innerWidth = Math.max(40, width - margin.left - margin.right)
    const innerHeight = Math.max(24, height - margin.top - margin.bottom)
    const values = points.map((point) => point.value).filter(Number.isFinite)
    const mustInclude: number[] = []
    const recent = points.slice(-30)
    for (const point of recent) if (Number.isFinite(point.value)) mustInclude.push(point.value)
    if (forecast && isLive) mustInclude.push(...Object.values(forecast.eta_quantiles))
    if (showTarget) mustInclude.push(run.target_value)
    const [yMin, yMax] = robustDomain(values, mustInclude)

    const x = d3
      .scaleLinear()
      .domain([0, run.budget_steps])
      .range([margin.left, margin.left + innerWidth])
    const y = d3
      .scaleLinear()
      .domain([yMin, yMax])
      .range([margin.top + innerHeight, margin.top])

    const line = d3
      .line<MetricPoint>()
      .x((point) => x(point.step))
      .y((point) => y(point.value))
    const path = points.length ? (line(points) ?? '') : ''

    const floor = margin.top + innerHeight
    const area = d3
      .area<MetricPoint>()
      .x((point) => x(point.step))
      .y0(floor)
      .y1((point) => y(point.value))
    const scrim = points.length ? (area(points) ?? '') : ''

    const last = points.at(-1)
    const headPoint = last ? { x: x(last.step), y: y(last.value) } : null

    let localSlope = 0
    if (points.length >= 5 && headPoint) {
      const tail = points.slice(-5)
      const dx = x(tail.at(-1)!.step) - x(tail[0].step)
      const dy = y(tail.at(-1)!.value) - y(tail[0].value)
      localSlope = dx > 0 ? dy / dx : 0
    }

    const geometry: FanGeometry | null =
      headPoint && forecast && isLive
        ? {
            headX: headPoint.x,
            headY: headPoint.y,
            slope: localSlope,
            endX: x(run.budget_steps),
            yScale: y,
          }
        : null

    return { xScale: x, yScale: y, linePath: path, areaPath: scrim, head: headPoint, fanGeometry: geometry }
  }, [points, forecast, run, width, height, margin, showTarget, isLive])

  const xTicks = compact ? [] : xScale.ticks(Math.max(3, Math.min(8, Math.floor(width / 140))))
  const yTicks = compact ? [] : yScale.ticks(5)
  const last = points.at(-1)
  const ariaLabel = last
    ? `${run.target_metric} ${fmtMetric(last.value)} at step ${fmtStep(last.step)}` +
      (forecast
        ? `; P(hit target) ${fmtProb(forecast.p_hit_target)}, median final ${fmtMetric(
            forecast.eta_quantiles.q50,
          )}`
        : '')
    : `no ${run.target_metric} data yet`
  const plotBottom = height - margin.bottom

  return (
    <div ref={ref} className="h-full w-full">
      <svg
        width={width}
        height={height}
        className="block"
        role="img"
        aria-label={ariaLabel}
        style={{ background: compact ? 'transparent' : 'var(--ink-well)' }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--bronze)" />
            <stop offset="100%" stopColor={visual.colorVar} />
          </linearGradient>
          <linearGradient id={`${gradientId}-scrim`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={visual.colorVar} stopOpacity="0.10" />
            <stop offset="100%" stopColor={visual.colorVar} stopOpacity="0" />
          </linearGradient>
          <clipPath id={`${gradientId}-clip`}>
            <rect
              x={margin.left}
              y={margin.top - 2}
              width={Math.max(0, width - margin.left - margin.right)}
              height={Math.max(0, height - margin.top - margin.bottom + 4)}
            />
          </clipPath>
        </defs>

        {!compact &&
          yTicks.map((tick) => (
            <g key={`y${tick}`}>
              <line
                x1={margin.left}
                x2={width - margin.right}
                y1={yScale(tick)}
                y2={yScale(tick)}
                stroke="var(--bronze-ghost, rgba(138,111,63,0.14))"
                strokeWidth="1"
              />
              <line
                x1={width - margin.right}
                x2={width - margin.right + 4}
                y1={yScale(tick)}
                y2={yScale(tick)}
                stroke="var(--bronze-faint)"
                strokeWidth="1"
              />
              <text
                x={width - margin.right + 7}
                y={yScale(tick) + 3}
                fill="var(--parchment)"
                fontSize="10"
                fontFamily="IBM Plex Mono, monospace"
              >
                {fmtMetric(tick)}
              </text>
            </g>
          ))}
        {!compact && (
          <line
            x1={margin.left}
            x2={width - margin.right}
            y1={plotBottom}
            y2={plotBottom}
            stroke="var(--bronze-faint)"
            strokeWidth="1"
          />
        )}
        {!compact &&
          xTicks.map((tick) => (
            <g key={`x${tick}`}>
              <line
                x1={xScale(tick)}
                x2={xScale(tick)}
                y1={plotBottom}
                y2={plotBottom + 4}
                stroke="var(--bronze-faint)"
                strokeWidth="1"
              />
              <text
                x={xScale(tick)}
                y={height - 7}
                fill="var(--parchment)"
                fontSize="10"
                textAnchor="middle"
                fontFamily="IBM Plex Mono, monospace"
              >
                {fmtStep(tick)}
              </text>
            </g>
          ))}

        {showTarget && (
          <g>
            <line
              x1={margin.left}
              x2={width - margin.right}
              y1={yScale(run.target_value)}
              y2={yScale(run.target_value)}
              stroke="var(--bone)"
              strokeWidth="1"
              strokeDasharray="5 5"
              opacity="0.5"
            />
            {!compact && (
              <text
                x={margin.left + 4}
                y={yScale(run.target_value) - 5}
                fill="var(--bone)"
                opacity="0.55"
                fontSize="9"
                fontFamily="IBM Plex Mono, monospace"
              >
                target {fmtMetric(run.target_value)}
              </text>
            )}
          </g>
        )}

        <g clipPath={`url(#${gradientId}-clip)`}>
          {areaPath && !compact && <path d={areaPath} fill={`url(#${gradientId}-scrim)`} />}

          {fanGeometry && forecast && (
            <PrognosisFan
              geometry={fanGeometry}
              forecast={forecast}
              statusColor={visual.colorVar}
              gradientId={gradientId}
            />
          )}

          {linePath && (
            <path d={linePath} fill="none" stroke="var(--bone)" strokeWidth={compact ? 1 : 1.4} />
          )}
        </g>

        {head && isLive && (
          <g>
            <circle cx={head.x} cy={head.y} r={compact ? 7 : 11} fill={visual.colorVar} opacity="0.12" />
            <circle
              className="comet-halo"
              cx={head.x}
              cy={head.y}
              r={compact ? 4 : 6}
              fill={visual.colorVar}
              opacity="0.35"
            />
            <circle cx={head.x} cy={head.y} r={2.5} fill={visual.colorVar} />
          </g>
        )}
      </svg>
    </div>
  )
}
