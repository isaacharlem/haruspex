// Keys: the dashboard's own key, and admin key management.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useApiKeys } from '../hooks/queries'
import { api, ApiError } from '../lib/api'
import type { ApiKeyCreated } from '../lib/types'
import { fmtTime } from '../lib/format'
import { useKeyStore } from '../state/keyStore'
import { useUiStore } from '../state/uiStore'

const ALL_SCOPES = ['ingest', 'read', 'admin']

export function KeysPage() {
  const storedKey = useKeyStore((state) => state.key)
  const clearKey = useKeyStore((state) => state.clearKey)
  const keys = useApiKeys()
  const queryClient = useQueryClient()
  const pushToast = useUiStore((state) => state.pushToast)

  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['read'])
  const [created, setCreated] = useState<ApiKeyCreated | null>(null)

  const create = useMutation({
    mutationFn: () => api.createKey(name.trim(), scopes),
    onSuccess: (key) => {
      setCreated(key)
      setName('')
      void queryClient.invalidateQueries({ queryKey: ['keys'] })
    },
    onError: (error) =>
      pushToast(error instanceof ApiError ? error.message : 'Key creation failed', 'warn'),
  })
  const revoke = useMutation({
    mutationFn: api.revokeKey,
    onSuccess: () => {
      pushToast('Key revoked')
      void queryClient.invalidateQueries({ queryKey: ['keys'] })
    },
  })

  const adminDenied = keys.error instanceof ApiError && keys.error.status === 403

  return (
    <div>
      <h1 className="font-display text-2xl text-bone">Keys</h1>

      <section className="mt-5 max-w-xl" aria-label="dashboard key">
        <h2 className="font-body text-[11px] font-semibold uppercase tracking-[0.08em] text-parchment">
          This dashboard
        </h2>
        <p className="mt-1 font-body text-xs text-parchment">
          Connected with <span className="font-mono text-bone">{storedKey.slice(0, 8)}…</span>{' '}
          (stored in this browser only).
        </p>
        <button
          type="button"
          onClick={() => {
            clearKey()
          }}
          className="mt-2 border px-3 py-1.5 font-body text-xs text-parchment hover:text-bone"
          style={{ borderColor: 'var(--bronze-faint)' }}
        >
          Disconnect and re-enter key
        </button>
      </section>

      <section className="mt-8" aria-label="api keys">
        <h2 className="font-body text-[11px] font-semibold uppercase tracking-[0.08em] text-parchment">
          API keys
        </h2>

        {adminDenied ? (
          <p className="mt-2 font-body text-xs text-parchment">
            Key management needs a key with the <span className="font-mono">admin</span> scope.
            Reconnect with an admin key to manage keys here.
          </p>
        ) : (
          <>
            <form
              className="mt-3 flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault()
                if (name.trim()) create.mutate()
              }}
            >
              <label className="block font-body text-[11px] text-parchment" htmlFor="key-name">
                Name
                <input
                  id="key-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-1 block w-48 border bg-ink-well px-2 py-1.5 font-mono text-xs text-bone"
                  style={{ borderColor: 'var(--bronze-faint)' }}
                />
              </label>
              <fieldset className="flex items-center gap-3">
                <legend className="font-body text-[11px] text-parchment">Scopes</legend>
                {ALL_SCOPES.map((scope) => (
                  <label key={scope} className="flex items-center gap-1 font-mono text-xs text-bone">
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      onChange={(event) =>
                        setScopes((current) =>
                          event.target.checked
                            ? [...current, scope]
                            : current.filter((item) => item !== scope),
                        )
                      }
                    />
                    {scope}
                  </label>
                ))}
              </fieldset>
              <button
                type="submit"
                disabled={!name.trim() || scopes.length === 0 || create.isPending}
                className="border px-3 py-1.5 font-body text-xs text-bone disabled:opacity-40"
                style={{ borderColor: 'var(--bronze)' }}
              >
                Create key
              </button>
            </form>

            {created && (
              <div
                className="mt-3 max-w-xl border p-3"
                style={{ borderColor: 'var(--ochre)' }}
                role="alert"
              >
                <p className="font-body text-xs text-bone">
                  Copy this key now — it is shown exactly once.
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate bg-ink-well px-2 py-1 font-mono text-xs text-bone">
                    {created.key}
                  </code>
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard.writeText(created.key)
                      pushToast('Key copied')
                    }}
                    className="border px-2 py-1 font-body text-xs text-parchment hover:text-bone"
                    style={{ borderColor: 'var(--bronze-faint)' }}
                  >
                    Copy
                  </button>
                  <button
                    type="button"
                    onClick={() => setCreated(null)}
                    className="border px-2 py-1 font-body text-xs text-parchment hover:text-bone"
                    style={{ borderColor: 'var(--bronze-faint)' }}
                  >
                    Done
                  </button>
                </div>
              </div>
            )}

            <table className="mt-4 w-full max-w-2xl font-mono text-xs">
              <thead>
                <tr className="text-left text-parchment">
                  <th className="py-2 pr-4 font-normal">name</th>
                  <th className="py-2 pr-4 font-normal">prefix</th>
                  <th className="py-2 pr-4 font-normal">scopes</th>
                  <th className="py-2 pr-4 font-normal">created</th>
                  <th className="py-2 font-normal" aria-label="actions" />
                </tr>
              </thead>
              <tbody>
                {(keys.data ?? []).map((key) => (
                  <tr
                    key={key.id}
                    className="border-t text-bone"
                    style={{ borderColor: 'var(--bronze-faint)' }}
                  >
                    <td className="py-2 pr-4">{key.name}</td>
                    <td className="py-2 pr-4">{key.key_prefix}…</td>
                    <td className="py-2 pr-4 text-parchment">{key.scopes.join(', ')}</td>
                    <td className="py-2 pr-4 text-parchment">{fmtTime(key.created_at)}</td>
                    <td className="py-2 text-right">
                      {key.revoked_at ? (
                        <span className="text-parchment">revoked</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => revoke.mutate(key.id)}
                          className="text-parchment hover:text-[var(--oxblood)]"
                        >
                          revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  )
}
