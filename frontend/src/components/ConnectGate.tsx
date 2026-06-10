// First-visit gate: the dashboard needs an API key with the read scope.

import { useState } from 'react'
import { useKeyStore } from '../state/keyStore'

export function ConnectGate() {
  const setKey = useKeyStore((state) => state.setKey)
  const [draft, setDraft] = useState('')

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink p-6">
      <div
        className="w-full max-w-md border bg-ink-raised p-6"
        style={{ borderColor: 'var(--bronze)' }}
      >
        <h1 className="font-display text-2xl text-bone">Haruspex</h1>
        <p className="mt-2 font-body text-xs text-parchment">
          Connect this dashboard with an API key that has the <span className="font-mono">read</span>{' '}
          scope. <code className="font-mono">make demo</code> prints one; or mint one with{' '}
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
            className="min-w-0 flex-1 border bg-ink-well px-2 py-1.5 font-mono text-sm text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="submit"
            disabled={!draft.trim().startsWith('hx_')}
            className="border px-3 py-1.5 font-body text-xs text-bone disabled:opacity-40"
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
