// Designed empty states that invite action: an etched augural sigil over a
// dashed votive border.

import type { ReactNode } from 'react'

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint: string
  action?: ReactNode
}) {
  return (
    <div
      className="flex flex-col items-center gap-3 border border-dashed px-6 py-14 text-center"
      style={{ borderColor: 'var(--bronze-faint)' }}
    >
      <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden="true" className="opacity-80">
        <circle
          cx="28"
          cy="28"
          r="24"
          fill="none"
          stroke="var(--bronze-faint)"
          strokeWidth="1"
          strokeDasharray="3 5"
        />
        <circle cx="28" cy="28" r="15" fill="none" stroke="var(--bronze)" strokeWidth="0.8" />
        <path
          d="M28 13 L28 20 M28 36 L28 43 M13 28 L20 28 M36 28 L43 28"
          stroke="var(--bronze)"
          strokeWidth="0.8"
        />
        <circle cx="28" cy="28" r="2.5" fill="var(--bronze)" />
        <path
          d="M28 28 Q36 22 43 24"
          fill="none"
          stroke="var(--parchment)"
          strokeWidth="1"
          opacity="0.6"
        />
      </svg>
      <p className="font-display text-base text-bone">{title}</p>
      <p className="max-w-sm font-body text-xs leading-relaxed text-parchment">{hint}</p>
      {action}
    </div>
  )
}
