// Type-the-run-name confirmation. Shows the grace period and checkpoint age
// so the operator knows exactly what the kill will and won't lose.

import { useEffect, useRef, useState } from 'react'
import { fmtAge } from '../lib/format'
import type { Run } from '../lib/types'

export function KillConfirmDialog({
  run,
  onConfirm,
  onClose,
}: {
  run: Run
  onConfirm: (graceSeconds: number) => void
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const [grace, setGrace] = useState(120)
  const inputRef = useRef<HTMLInputElement>(null)
  const armed = typed === run.name

  useEffect(() => {
    inputRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Kill run ${run.name}`}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md border bg-ink-raised p-5"
        style={{ borderColor: 'var(--oxblood)' }}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="font-display text-xl text-bone">Kill run</h2>
        <p className="mt-2 font-body text-xs text-parchment">
          The kill directive reaches the trainer on its next heartbeat. It has{' '}
          <span className="font-mono text-bone">{grace}s</span> of grace to checkpoint and stop.
          Last checkpoint: <span className="font-mono text-bone">{fmtAge(run.last_checkpoint_at)}</span>.
        </p>

        <label className="mt-4 block font-body text-xs text-parchment" htmlFor="kill-grace">
          Grace period (seconds)
          <input
            id="kill-grace"
            type="number"
            min={0}
            max={3600}
            value={grace}
            onChange={(event) => setGrace(Number(event.target.value))}
            className="mt-1 w-full border bg-ink-well px-2 py-1.5 font-mono text-sm text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
          />
        </label>

        <label className="mt-3 block font-body text-xs text-parchment" htmlFor="kill-name">
          Type <span className="font-mono text-bone">{run.name}</span> to confirm
          <input
            id="kill-name"
            ref={inputRef}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            className="mt-1 w-full border bg-ink-well px-2 py-1.5 font-mono text-sm text-bone"
            style={{ borderColor: armed ? 'var(--oxblood)' : 'var(--bronze-faint)' }}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="border px-3 py-1.5 font-body text-xs text-parchment hover:text-bone"
            style={{ borderColor: 'var(--bronze-faint)' }}
          >
            Keep running
          </button>
          <button
            type="button"
            disabled={!armed}
            onClick={() => onConfirm(grace)}
            className="border px-3 py-1.5 font-body text-xs disabled:cursor-not-allowed disabled:opacity-40"
            style={{ borderColor: 'var(--oxblood)', color: 'var(--oxblood)' }}
            data-testid="confirm-kill"
          >
            Kill run
          </button>
        </div>
      </div>
    </div>
  )
}
