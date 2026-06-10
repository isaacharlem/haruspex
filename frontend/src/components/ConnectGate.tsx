// First-visit gate: the dashboard needs an API key with the read scope.
// A single ceremonial tablet, centered in the dark.

import { useState } from 'react'
import { useKeyStore } from '../state/keyStore'

export function ConnectGate() {
  const setKey = useKeyStore((state) => state.setKey)
  const [draft, setDraft] = useState('')

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="tablet fade-up w-full max-w-md p-7">
        <div className="flex items-center gap-3">
          <svg width="34" height="34" viewBox="0 0 34 34" aria-hidden="true">
            <circle cx="17" cy="17" r="14" fill="none" stroke="var(--bronze)" strokeWidth="1" />
            <circle
              cx="17"
              cy="17"
              r="9"
              fill="none"
              stroke="var(--bronze-faint)"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
            <circle cx="17" cy="17" r="1.8" fill="var(--bronze)" />
            <path
              d="M17 17 Q23 12 28 13"
              fill="none"
              stroke="var(--bone)"
              strokeWidth="1"
              opacity="0.7"
            />
          </svg>
          <div>
            <h1 className="font-display text-2xl font-medium tracking-tight text-bone">
              Haruspex
            </h1>
            <p className="font-mono text-[10px] tracking-[0.18em] text-bronze uppercase">
              run-fate forecasting
            </p>
          </div>
        </div>
        <div className="etched-rule mt-4" aria-hidden="true" />
        <p className="mt-4 font-body text-xs leading-relaxed text-parchment">
          Connect this dashboard with an API key that has the{' '}
          <span className="font-mono">read</span> scope.{' '}
          <code className="font-mono">make demo</code> prints one; or mint one with{' '}
          <code className="font-mono">make keys</code>. The key stays in this browser.
        </p>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (draft.trim()) setKey(draft.trim())
          }}
        >
          <label className="sr-only" htmlFor="api-key-input">
            API key
          </label>
          <input
            id="api-key-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="min-w-0 flex-1 border bg-ink-well px-2.5 py-1.5 font-mono text-sm text-bone transition-colors hover:border-bronze"
            style={{ borderColor: 'var(--bronze-faint)' }}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="submit"
            disabled={!draft.trim().startsWith('hx_')}
            className="border px-3.5 py-1.5 font-body text-xs text-bone transition-colors hover:bg-ink-well disabled:opacity-40"
            style={{ borderColor: 'var(--bronze)' }}
          >
            Connect
          </button>
        </form>
        {draft && !draft.trim().startsWith('hx_') && (
          <p className="mt-2 font-body text-[11px]" style={{ color: 'var(--ochre)' }}>
            Haruspex keys start with hx_ — check for a copy-paste miss.
          </p>
        )}
      </div>
    </div>
  )
}
