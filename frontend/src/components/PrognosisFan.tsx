// The signature element: from the trace head, quantile lines fan toward
// budget-end like an augural diagram. Bézier continuations of the local
// slope, bronze fading into the status color, median brighter. Redraws tween
// 400ms on each forecast refresh (snap under prefers-reduced-motion).

import * as d3 from 'd3'
import { useEffect, useMemo, useRef } from 'react'
import type { Forecast } from '../lib/types'

export interface FanGeometry {
  headX: number
  headY: number
  slope: number
  endX: number
  yScale: (value: number) => number
}

const QUANTILE_KEYS = ['q10', 'q25', 'q50', 'q75', 'q90'] as const

function fanPath(geometry: FanGeometry, endValue: number): string {
  const { headX, headY, slope, endX } = geometry
  const endY = geometry.yScale(endValue)
  const dx = (endX - headX) * 0.35
  const controlX = headX + dx
  const controlY = headY + slope * dx
  return `M${headX},${headY} Q${controlX},${controlY} ${endX},${endY}`
}

function envelopePath(geometry: FanGeometry, low: number, high: number): string {
  const { headX, headY, slope, endX } = geometry
  const dx = (endX - headX) * 0.35
  const controlX = headX + dx
  const controlY = headY + slope * dx
  const lowY = geometry.yScale(low)
  const highY = geometry.yScale(high)
  return [
    `M${headX},${headY}`,
    `Q${controlX},${controlY} ${endX},${highY}`,
    `L${endX},${lowY}`,
    `Q${controlX},${controlY} ${headX},${headY}`,
    'Z',
  ].join(' ')
}

export function PrognosisFan({
  geometry,
  forecast,
  statusColor,
  gradientId,
}: {
  geometry: FanGeometry
  forecast: Forecast
  statusColor: string
  gradientId: string
}) {
  const group = useRef<SVGGElement>(null)
  const quantiles = forecast.eta_quantiles
  const reduceMotion = useMemo(
    () =>
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  useEffect(() => {
    if (!group.current) return
    const root = d3.select(group.current)
    const duration = reduceMotion ? 0 : 400
    const ease = d3.easeCubicInOut

    const envelope = envelopePath(geometry, quantiles.q10 ?? 0, quantiles.q90 ?? 0)
    root
      .select<SVGPathElement>('path[data-fan=envelope]')
      .transition()
      .duration(duration)
      .ease(ease)
      .attr('d', envelope)

    for (const key of QUANTILE_KEYS) {
      const value = quantiles[key]
      if (value === undefined) continue
      root
        .select<SVGPathElement>(`path[data-fan=${key}]`)
        .transition()
        .duration(duration)
        .ease(ease)
        .attr('d', fanPath(geometry, value))
    }
  }, [geometry, quantiles, reduceMotion])

  return (
    <g ref={group} aria-hidden="true">
      <path data-fan="envelope" fill={statusColor} opacity={0.07} stroke="none" />
      {QUANTILE_KEYS.map((key) => (
        <path
          key={key}
          data-fan={key}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={key === 'q50' ? 1.5 : 1}
          opacity={key === 'q50' ? 1 : 0.7}
        />
      ))}
    </g>
  )
}
