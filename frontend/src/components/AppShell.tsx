// Shell: left rail (bottom bar on small screens), content, toasts, the
// Analyst dock. One SSE subscription lives here.

import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useEventStream } from '../hooks/useEventStream'
import { useUiStore } from '../state/uiStore'
import { Toasts } from './Toasts'

const NAV = [
  { to: '/', label: 'Fleet', glyph: '◉' },
  { to: '/policies', label: 'Policies', glyph: '⚖' },
  { to: '/calibration', label: 'Calibration', glyph: '◬' },
  { to: '/ledger', label: 'Ledger', glyph: '$' },
  { to: '/settings/keys', label: 'Keys', glyph: '⚿' },
]

export function AppShell({ copilot }: { copilot?: ReactNode }) {
  useEventStream()
  const streamConnected = useUiStore((state) => state.streamConnected)

  return (
    <div className="flex min-h-screen flex-col bg-ink sm:flex-row">
      <nav
        aria-label="primary"
        className="order-last flex shrink-0 justify-around border-t sm:order-first sm:w-14 sm:flex-col sm:justify-start sm:gap-1 sm:border-t-0 sm:border-r sm:pt-3"
        style={{ borderColor: 'var(--bronze-faint)' }}
      >
        <NavLink to="/" className="hidden px-2 py-3 text-center sm:block" aria-label="Haruspex home">
          <span className="font-display text-lg text-bone" aria-hidden="true">
            H
          </span>
        </NavLink>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-2 py-2 font-body text-[9px] uppercase tracking-wide ${
                isActive ? 'text-bone' : 'text-parchment hover:text-bone'
              }`
            }
          >
            <span className="text-base" aria-hidden="true">
              {item.glyph}
            </span>
            {item.label}
          </NavLink>
        ))}
        <span
          className="mt-auto hidden px-2 pb-3 text-center font-mono text-[9px] sm:block"
          style={{ color: streamConnected ? 'var(--verdigris)' : 'var(--ochre)' }}
          title={streamConnected ? 'live stream connected' : 'live stream reconnecting'}
        >
          {streamConnected ? '◉ live' : '◌ sync'}
        </span>
      </nav>

      <main className="min-w-0 flex-1 p-4 sm:p-6">
        <Outlet />
      </main>

      {copilot}
      <Toasts />
    </div>
  )
}
