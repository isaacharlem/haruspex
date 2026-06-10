// Designed empty states that invite action.

import type { ReactNode } from 'react'

export function EmptyState({ title, hint, action }: { title: string; hint: string; action?: ReactNode }) {
  return (
    <div
      className="flex flex-col items-center gap-2 border border-dashed px-6 py-12 text-center"
      style={{ borderColor: 'var(--bronze-faint)' }}
    >
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <circle cx="14" cy="14" r="11" fill="none" stroke="var(--bronze)" strokeWidth="1" strokeDasharray="3 4" />
        <circle cx="14" cy="14" r="2" fill="var(--bronze)" />
      </svg>
      <p className="font-body text-sm text-bone">{title}</p>
      <p className="max-w-sm font-body text-xs text-parchment">{hint}</p>
      {action}
    </div>
  )
}
