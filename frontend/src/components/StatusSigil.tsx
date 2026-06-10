// Etched status glyph + label. Color never travels alone.

import type { StatusVisual } from '../lib/status'

function Glyph({ visual }: { visual: StatusVisual }) {
  const stroke = visual.colorVar
  switch (visual.sigil) {
    case 'circle':
      return <circle cx="6" cy="6" r="4" fill={stroke} />
    case 'triangle':
      return <path d="M6 1.8 L11 10.2 L1 10.2 Z" fill="none" stroke={stroke} strokeWidth="1.5" />
    case 'saltire':
      return (
        <path d="M2 2 L10 10 M10 2 L2 10" stroke={stroke} strokeWidth="1.7" strokeLinecap="round" />
      )
    case 'diamond':
      return <path d="M6 1 L11 6 L6 11 L1 6 Z" fill={stroke} />
    case 'slashed':
      return (
        <g stroke={stroke} strokeWidth="1.5" fill="none">
          <circle cx="6" cy="6" r="4.2" />
          <path d="M2.8 9.2 L9.2 2.8" />
        </g>
      )
    default:
      return (
        <circle cx="6" cy="6" r="4.2" fill="none" stroke={stroke} strokeWidth="1.4" strokeDasharray="2 2.4" />
      )
  }
}

export function StatusSigil({ visual, compact = false }: { visual: StatusVisual; compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5" role="status" aria-label={`status ${visual.label}`}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <Glyph visual={visual} />
      </svg>
      {!compact && (
        <span
          className="font-mono text-[10px] tracking-[0.08em]"
          style={{ color: visual.colorVar }}
        >
          {visual.label}
        </span>
      )}
    </span>
  )
}
