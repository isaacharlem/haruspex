// The instrument: live metric trace with etched axes, target hairline,
// comet head, and the prognosis fan toward budget-end.

import * as d3 from 'd3'
import { useId, useMemo } from 'react'
import { fmtMetric, fmtProb, fmtStep } from '../lib/format'
import type { Forecast, MetricPoint, Run } from '../lib/types'
import { runStatusVisual } from '../lib/status'
import { PrognosisFan, type FanGeometry } from './PrognosisFan'

interface TraceCanvasProps {
  run: Run
  points: MetricPoint[]
  forecast: Forecast | null
  showTarget: boolean
  compact?: boolean
  height?: number
}

const MARGIN = { top: 10, right: 44, bottom: 22, left: 8 }
const COMPACT_MARGIN = { top: 4, right: 2, bottom: 4, left: 2 }

export function TraceCanvas({
  run,
  points,
  forecast,
  showTarget,
  compact = false,
  height = compact ? 64 : 320,
}: TraceCanvasProps) {
  const gradientId = useId().replace(/:/g, '')
  const width = compact ? 280 : 760
  const margin = compact ? COMPACT_MARGIN : MARGIN
  const visual = runStatusVisual(run)
  const isLive = run.status === 'RUNNING'

  const { xScale, yScale, linePath, head, slope, fanGeometry } = useMemo(() => {
    const innerWidth = width - margin.left - margin.right
    const innerHeight = height - margin.top - margin.bottom
    const values = points.map((point) => point.value)
    const quantileValues =
      forecast && isLive ? Object.values(forecast.eta_quantiles) : []
    const yDomainValues = [...values, ...quantileValues]
    if (showTarget) yDomainValues.push(run.target_value)
    const [yMin, yMax] = d3.extent(yDomainValues.length ? yDomainValues : [0, 1]) as [
      number,
      number,
    ]
    const pad = (yMax - yMin || 1) * 0.08
    const x = d3
      .scaleLinear()
      .domain([0, run.budget_steps])
      .range([margin.left, margin.left + innerWidth])
    const y = d3
      .scaleLinear()
      .domain([yMin - pad, yMax + pad])
      .range([margin.top + innerHeight, margin.top])

    const line = d3
      .line<MetricPoint>()
      .x((point) => x(point.step))
      .y((point) => y(point.value))
    const path = points.length ? (line(points) ?? '') : ''

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

    return {
      xScale: x,
      yScale: y,
      linePath: path,
      head: headPoint,
      slope: localSlope,
      fanGeometry: geometry,
    }
  }, [points, forecast, run, width, height, margin, showTarget, isLive])

  void slope
  const xTicks = compact ? [] : xScale.ticks(5)
  const yTicks = compact ? [] : yScale.ticks(4)
  const last = points.at(-1)
  const ariaLabel = last
    ? `${run.target_metric} ${fmtMetric(last.value)} at step ${fmtStep(last.step)}` +
      (forecast
        ? `; P(hit target) ${fmtProb(forecast.p_hit_target)}, median final ${fmtMetric(
            forecast.eta_quantiles.q50,
          )}`
        : '')
    : `no ${run.target_metric} data yet`

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="block w-full"
      role="img"
      aria-label={ariaLabel}
      style={{ background: compact ? 'transparent' : 'var(--ink-well)' }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--bronze)" />
          <stop offset="100%" stopColor={visual.colorVar} />
        </linearGradient>
      </defs>

      {!compact &&
        yTicks.map((tick) => (
          <g key={`y${tick}`}>
            <line
              x1={margin.left}
              x2={width - margin.right}
              y1={yScale(tick)}
              y2={yScale(tick)}
              stroke="var(--bronze-faint)"
              strokeWidth="0.5"
            />
            <text
              x={width - margin.right + 6}
              y={yScale(tick) + 3}
              fill="var(--parchment)"
              fontSize="10"
              fontFamily="IBM Plex Mono, monospace"
            >
              {fmtMetric(tick)}
            </text>
          </g>
        ))}
      {!compact &&
        xTicks.map((tick) => (
          <text
            key={`x${tick}`}
            x={xScale(tick)}
            y={height - 6}
            fill="var(--parchment)"
            fontSize="10"
            textAnchor="middle"
            fontFamily="IBM Plex Mono, monospace"
          >
            {fmtStep(tick)}
          </text>
        ))}

      {showTarget && (
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
      )}

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

      {head && isLive && (
        <g>
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
  )
}
