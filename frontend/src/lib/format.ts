// Formatting: probabilities to two decimals, dollars whole, steps compact.

export function fmtProb(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return '—'
  return p.toFixed(2)
}

export function fmtUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `$${Math.round(value).toLocaleString('en-US')}`
}

export function fmtStep(step: number): string {
  if (step >= 1_000_000) return `${(step / 1_000_000).toFixed(1)}M`
  if (step >= 10_000) return `${Math.round(step / 1000)}k`
  if (step >= 1_000) return `${(step / 1000).toFixed(1)}k`
  return String(step)
}

export function fmtMetric(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs !== 0 && (abs < 0.001 || abs >= 100_000)) return value.toExponential(2)
  return value.toPrecision(4)
}

export function fmtRate(usdPerHour: number): string {
  return `$${usdPerHour % 1 === 0 ? usdPerHour : usdPerHour.toFixed(2)}/hr`
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function fmtAge(iso: string | null): string {
  if (!iso) return 'never'
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${Math.round(seconds)}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${(seconds / 3600).toFixed(1)}h ago`
}

export function fmtPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}
