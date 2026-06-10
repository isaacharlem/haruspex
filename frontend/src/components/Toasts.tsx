// Polite toast stack, bottom-left, four max, auto-dismissing.

import { useUiStore } from '../state/uiStore'

const TONE_COLOR: Record<string, string> = {
  info: 'var(--verdigris)',
  warn: 'var(--ochre)',
  kill: 'var(--oxblood)',
}

export function Toasts() {
  const toasts = useUiStore((state) => state.toasts)
  const dismiss = useUiStore((state) => state.dismissToast)
  return (
    <div
      className="fixed bottom-4 left-4 z-50 flex w-72 flex-col gap-2"
      role="status"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <button
          key={toast.id}
          type="button"
          onClick={() => dismiss(toast.id)}
          className="flex items-center gap-2 border bg-ink-raised px-3 py-2 text-left font-body text-xs text-bone shadow-lg"
          style={{ borderColor: TONE_COLOR[toast.tone] }}
          data-testid="toast"
        >
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ background: TONE_COLOR[toast.tone] }}
            aria-hidden="true"
          />
          {toast.message}
        </button>
      ))}
    </div>
  )
}
