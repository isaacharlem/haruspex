// Policies: master list left, editor right, dry-run drawer below.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { PolicyEditor } from '../components/PolicyEditor'
import { KILL_DOOMED_TEMPLATE } from '../lib/policyTemplates'
import { usePolicies } from '../hooks/queries'
import { api, ApiError } from '../lib/api'
import type { PolicyDefinition } from '../lib/types'
import { useUiStore } from '../state/uiStore'

export function PoliciesPage() {
  const policies = usePolicies()
  const [selectedId, setSelectedId] = useState<number | 'new' | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const pushToast = useUiStore((state) => state.pushToast)

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['policies'] })

  const create = useMutation({
    mutationFn: (definition: PolicyDefinition) => api.createPolicy(definition),
    onSuccess: (policy) => {
      invalidate()
      setSelectedId(policy.id)
      setServerError(null)
      pushToast(`Policy ${policy.name} created`)
    },
    onError: (error) =>
      setServerError(error instanceof ApiError ? error.message : 'The API rejected this policy.'),
  })
  const update = useMutation({
    mutationFn: ({ id, definition }: { id: number; definition: PolicyDefinition }) =>
      api.updatePolicy(id, { definition }),
    onSuccess: (policy) => {
      invalidate()
      setServerError(null)
      pushToast(`Policy ${policy.name} saved (v${policy.version})`)
    },
    onError: (error) =>
      setServerError(error instanceof ApiError ? error.message : 'The API rejected this policy.'),
  })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.updatePolicy(id, { enabled }),
    onSuccess: invalidate,
  })

  const selected =
    selectedId === 'new' ? null : (policies.data?.find((policy) => policy.id === selectedId) ?? null)

  return (
    <div>
      <div className="flex items-end justify-between">
        <h1 className="font-display text-2xl text-bone">Policies</h1>
        <button
          type="button"
          onClick={() => {
            setSelectedId('new')
            setServerError(null)
          }}
          className="border px-3 py-1.5 font-body text-xs text-bone"
          style={{ borderColor: 'var(--bronze)' }}
          data-testid="new-policy"
        >
          New policy
        </button>
      </div>

      {policies.data?.length === 0 && selectedId === null ? (
        <div className="mt-8">
          <EmptyState
            title="No policies yet"
            hint="Create one — start from the kill-doomed template. A policy watches every refit and can warn or kill with a checkpoint guard."
            action={
              <button
                type="button"
                onClick={() => setSelectedId('new')}
                className="border px-3 py-1.5 font-body text-xs text-bone"
                style={{ borderColor: 'var(--bronze)' }}
              >
                Start from template
              </button>
            }
          />
        </div>
      ) : (
        <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
          <ul className="space-y-1" aria-label="policies">
            {(policies.data ?? []).map((policy) => (
              <li key={policy.id}>
                <div
                  className={`flex items-center gap-2 border px-2 py-2 ${
                    selectedId === policy.id ? 'bg-ink-raised' : ''
                  }`}
                  style={{
                    borderColor:
                      selectedId === policy.id ? 'var(--bronze)' : 'var(--bronze-faint)',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(policy.id)
                      setServerError(null)
                    }}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="block truncate font-body text-xs text-bone">
                      {policy.name}
                    </span>
                    <span className="font-mono text-[10px] text-parchment">
                      v{policy.version} · {policy.definition.action.type} ·{' '}
                      {policy.definition.scope.tags.length
                        ? policy.definition.scope.tags.map((tag) => `#${tag}`).join(' ')
                        : 'all runs'}
                    </span>
                  </button>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={policy.enabled}
                    aria-label={`${policy.name} enabled`}
                    onClick={() => toggle.mutate({ id: policy.id, enabled: !policy.enabled })}
                    className="font-mono text-[10px]"
                    style={{ color: policy.enabled ? 'var(--verdigris)' : 'var(--parchment)' }}
                  >
                    {policy.enabled ? '● on' : '○ off'}
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <div className="min-w-0">
            {selectedId === null ? (
              <p className="font-body text-xs text-parchment">
                Select a policy to edit, or create a new one.
              </p>
            ) : (
              <PolicyEditor
                key={selectedId}
                initial={selected ? selected.definition : KILL_DOOMED_TEMPLATE}
                saving={create.isPending || update.isPending}
                serverError={serverError}
                onSave={(definition) => {
                  if (selected) update.mutate({ id: selected.id, definition })
                  else create.mutate(definition)
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
