// Status taxonomy: sigil glyph + label + token color, always together —
// color is never the only channel.

import type { Health, Run, RunStatus } from './types'

export interface StatusVisual {
  sigil: 'circle' | 'triangle' | 'saltire' | 'diamond' | 'slashed' | 'dotted'
  label: string
  colorVar: string
}

export function statusVisual(status: RunStatus, health: Health | null): StatusVisual {
  if (status === 'RUNNING') {
    switch (health) {
      case 'DOOMED':
        return { sigil: 'saltire', label: 'DOOMED', colorVar: 'var(--oxblood)' }
      case 'AT_RISK':
        return { sigil: 'triangle', label: 'AT RISK', colorVar: 'var(--ochre)' }
      case 'HEALTHY':
        return { sigil: 'circle', label: 'HEALTHY', colorVar: 'var(--verdigris)' }
      default:
        return { sigil: 'dotted', label: 'AUGURING', colorVar: 'var(--parchment)' }
    }
  }
  switch (status) {
    case 'COMPLETED':
      return { sigil: 'diamond', label: 'COMPLETED', colorVar: 'var(--bone)' }
    case 'DIVERGED':
      return { sigil: 'saltire', label: 'DIVERGED', colorVar: 'var(--oxblood)' }
    case 'KILLED':
      return { sigil: 'slashed', label: 'KILLED', colorVar: 'var(--oxblood)' }
    default:
      return { sigil: 'dotted', label: 'LOST', colorVar: 'var(--parchment)' }
  }
}

export function runStatusVisual(run: Run): StatusVisual {
  return statusVisual(run.status, run.health)
}

const SEVERITY: Record<string, number> = {
  DOOMED: 0,
  'AT RISK': 1,
  AUGURING: 2,
  HEALTHY: 3,
  LOST: 4,
  KILLED: 5,
  DIVERGED: 6,
  COMPLETED: 7,
}

export function bySeverity(a: Run, b: Run): number {
  const live = (run: Run) => (run.status === 'RUNNING' ? 0 : 1)
  if (live(a) !== live(b)) return live(a) - live(b)
  const sa = SEVERITY[runStatusVisual(a).label] ?? 9
  const sb = SEVERITY[runStatusVisual(b).label] ?? 9
  if (sa !== sb) return sa - sb
  return b.id - a.id
}
