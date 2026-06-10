// Policy editor: constrained form <-> raw JSON, same definition underneath.
// Dry run opens a drawer replaying the candidate against history.

import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { DryRunResult, PolicyDefinition } from '../lib/types'
import { DryRunDrawer } from './DryRunDrawer'

const SIGNALS = ['p_hit_target', 'p_diverge', 'p_plateau', 'progress']
const OPS = ['<', '<=', '>', '>='] as const

function validateLocal(definition: PolicyDefinition): string | null {
  if (!definition.name?.trim()) return 'Name the policy.'
  const { when, action } = definition
  if (!when || !action) return 'Both when and action are required.'
  const signal = when.signal ?? ''
  if (!SIGNALS.includes(signal) && !/^metric:.+/.test(signal)) {
    return `Signal must be one of ${SIGNALS.join(', ')} or metric:<name>.`
  }
  if (!OPS.includes(when.op)) return 'Operator must be <, <=, > or >=.'
  if (typeof when.value !== 'number' || Number.isNaN(when.value)) return 'Threshold must be a number.'
  if (when.after_progress < 0 || when.after_progress > 1) return 'After-progress must be in [0, 1].'
  if (when.sustained_evals < 1) return 'Sustained evals must be at least 1.'
  if (action.type !== 'warn' && action.type !== 'kill') return 'Action must be warn or kill.'
  return null
}

export function PolicyEditor({
  initial,
  onSave,
  saving,
  serverError,
}: {
  initial: PolicyDefinition
  onSave: (definition: PolicyDefinition) => void
  saving: boolean
  serverError: string | null
}) {
  // Callers remount the editor per selection (key=selectedId), so `initial`
  // is fixed for this instance's lifetime.
  const [definition, setDefinition] = useState<PolicyDefinition>(initial)
  const [rawMode, setRawMode] = useState(false)
  const [rawText, setRawText] = useState(() => JSON.stringify(initial, null, 2))
  const [rawError, setRawError] = useState<string | null>(null)
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null)

  const localError = rawMode ? rawError : validateLocal(definition)

  const dryRun = useMutation({
    mutationFn: api.dryRunPolicy,
    onSuccess: setDryRunResult,
  })

  const update = (patch: Partial<PolicyDefinition>) => {
    const next = { ...definition, ...patch }
    setDefinition(next)
    setRawText(JSON.stringify(next, null, 2))
  }

  const updateWhen = (patch: Partial<PolicyDefinition['when']>) =>
    update({ when: { ...definition.when, ...patch } })
  const updateAction = (patch: Partial<PolicyDefinition['action']>) =>
    update({ action: { ...definition.action, ...patch } })

  const onRawChange = (text: string) => {
    setRawText(text)
    try {
      const parsed = JSON.parse(text) as PolicyDefinition
      setDefinition(parsed)
      setRawError(validateLocal(parsed))
    } catch {
      setRawError('Invalid JSON — fix the syntax to continue.')
    }
  }

  const field = 'mt-1 w-full border bg-ink-well px-2 py-1.5 font-mono text-xs text-bone'
  const fieldStyle = { borderColor: 'var(--bronze-faint)' }
  const labelCls = 'block font-body text-[11px] text-parchment'

  return (
    <div data-testid="policy-editor">
      <div className="flex items-center justify-between">
        <h3 className="font-body text-[11px] font-semibold uppercase tracking-[0.08em] text-parchment">
          Definition
        </h3>
        <button
          type="button"
          onClick={() => setRawMode((mode) => !mode)}
          className="border px-2 py-1 font-mono text-[10px] text-parchment hover:text-bone"
          style={fieldStyle}
        >
          {rawMode ? 'form view' : 'raw JSON'}
        </button>
      </div>

      {rawMode ? (
        <textarea
          value={rawText}
          onChange={(event) => onRawChange(event.target.value)}
          rows={18}
          spellCheck={false}
          aria-label="policy definition JSON"
          className="mt-2 w-full border bg-ink-well p-2 font-mono text-xs text-bone"
          style={fieldStyle}
        />
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-3">
          <label className={`${labelCls} col-span-2`}>
            Name
            <input
              value={definition.name}
              onChange={(event) => update({ name: event.target.value })}
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={`${labelCls} col-span-2`}>
            Scope tags (comma-separated; empty = all runs)
            <input
              value={definition.scope.tags.join(', ')}
              onChange={(event) =>
                update({
                  scope: {
                    tags: event.target.value
                      .split(',')
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  },
                })
              }
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={labelCls}>
            Signal
            <input
              value={definition.when.signal}
              onChange={(event) => updateWhen({ signal: event.target.value })}
              list="signal-options"
              className={field}
              style={fieldStyle}
            />
            <datalist id="signal-options">
              {SIGNALS.map((signal) => (
                <option key={signal} value={signal} />
              ))}
              <option value="metric:loss" />
            </datalist>
          </label>
          <label className={labelCls}>
            Operator
            <select
              value={definition.when.op}
              onChange={(event) =>
                updateWhen({ op: event.target.value as PolicyDefinition['when']['op'] })
              }
              className={field}
              style={fieldStyle}
            >
              {OPS.map((op) => (
                <option key={op}>{op}</option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            Threshold
            <input
              type="number"
              step="0.01"
              value={definition.when.value}
              onChange={(event) => updateWhen({ value: Number(event.target.value) })}
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={labelCls}>
            After progress (0–1)
            <input
              type="number"
              step="0.05"
              min={0}
              max={1}
              value={definition.when.after_progress}
              onChange={(event) => updateWhen({ after_progress: Number(event.target.value) })}
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={labelCls}>
            Sustained evals
            <input
              type="number"
              min={1}
              max={100}
              value={definition.when.sustained_evals}
              onChange={(event) => updateWhen({ sustained_evals: Number(event.target.value) })}
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={labelCls}>
            Action
            <select
              value={definition.action.type}
              onChange={(event) =>
                updateAction({ type: event.target.value as 'warn' | 'kill' })
              }
              className={field}
              style={fieldStyle}
            >
              <option value="warn">warn</option>
              <option value="kill">kill</option>
            </select>
          </label>
          <label className={labelCls}>
            Grace seconds
            <input
              type="number"
              min={0}
              max={3600}
              value={definition.action.grace_seconds}
              onChange={(event) => updateAction({ grace_seconds: Number(event.target.value) })}
              className={field}
              style={fieldStyle}
            />
          </label>
          <label className={labelCls}>
            Min checkpoint age (s)
            <input
              type="number"
              min={0}
              max={86400}
              value={definition.action.min_checkpoint_age_seconds}
              onChange={(event) =>
                updateAction({ min_checkpoint_age_seconds: Number(event.target.value) })
              }
              className={field}
              style={fieldStyle}
            />
          </label>
        </div>
      )}

      {(localError ?? serverError) && (
        <p className="mt-2 font-body text-xs" style={{ color: 'var(--oxblood)' }} role="alert">
          {localError ?? serverError}
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          disabled={Boolean(localError) || saving}
          onClick={() => onSave(definition)}
          className="border px-3 py-1.5 font-body text-xs text-bone disabled:opacity-40"
          style={{ borderColor: 'var(--bronze)' }}
          data-testid="save-policy"
        >
          {saving ? 'Saving…' : 'Save policy'}
        </button>
        <button
          type="button"
          disabled={Boolean(localError) || dryRun.isPending}
          onClick={() => dryRun.mutate(definition)}
          className="border px-3 py-1.5 font-body text-xs text-parchment hover:text-bone disabled:opacity-40"
          style={{ borderColor: 'var(--bronze-faint)' }}
          data-testid="dry-run"
        >
          {dryRun.isPending ? 'Replaying…' : 'Dry run against history'}
        </button>
      </div>
      {dryRun.error instanceof ApiError && (
        <p className="mt-2 font-body text-xs" style={{ color: 'var(--oxblood)' }}>
          {dryRun.error.message}
        </p>
      )}

      {dryRunResult && (
        <DryRunDrawer result={dryRunResult} onClose={() => setDryRunResult(null)} />
      )}
    </div>
  )
}
