// Shared page chrome: the title block over an etched double rule, and the
// small ornamented section heading used between content groups.

import type { ReactNode } from 'react'

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <header>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-[26px] font-medium tracking-tight text-bone">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1 max-w-xl font-body text-xs leading-relaxed text-parchment">
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div className="etched-rule mt-3" aria-hidden="true" />
    </header>
  )
}

export function SectionRule({ children }: { children: ReactNode }) {
  return (
    <h2 className="rune-rule font-body text-[11px] font-semibold tracking-[0.14em] text-parchment uppercase">
      {children}
    </h2>
  )
}
