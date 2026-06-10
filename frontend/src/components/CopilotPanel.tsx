// The Analyst: a dockable chat panel that talks through the dashboard.
// Right dock on wide screens, bottom sheet on small ones. Without a server
// key it renders a setup card — everything else works without it.

import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useCopilotStatus } from '../hooks/queries'
import { streamChat, type ChatTurnMessage } from '../lib/copilotStream'
import { useUiStore } from '../state/uiStore'

interface ToolChip {
  name: string
  args: Record<string, unknown>
}

interface PanelMessage extends ChatTurnMessage {
  tools?: ToolChip[]
}

const SUGGESTIONS = [
  'Which runs are at risk right now and why?',
  'Is the forecaster well calibrated?',
  'What did the kill policy save us this week?',
]

function chipLabel(chip: ToolChip): string {
  const args = Object.entries(chip.args)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(', ')
  return `${chip.name}(${args})`
}

export function CopilotPanel() {
  const open = useUiStore((state) => state.copilotOpen)
  const setOpen = useUiStore((state) => state.setCopilotOpen)
  const status = useCopilotStatus()
  const location = useLocation()
  const [messages, setMessages] = useState<PanelMessage[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (element && typeof element.scrollTo === 'function') {
      element.scrollTo({ top: element.scrollHeight })
    }
  }, [messages])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && open) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed right-4 bottom-16 z-30 border bg-ink-raised px-3 py-2 font-body text-xs text-bone shadow-lg sm:bottom-4"
        style={{ borderColor: 'var(--bronze)' }}
        data-testid="open-copilot"
      >
        ✦ Analyst
      </button>
    )
  }

  const send = (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    const runMatch = /\/runs\/(\d+)/.exec(location.pathname)
    const context: Record<string, unknown> = { route: location.pathname }
    if (runMatch) context.run_id = Number(runMatch[1])

    const history: ChatTurnMessage[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question },
    ]
    setMessages((current) => [
      ...current,
      { role: 'user', content: question },
      { role: 'assistant', content: '', tools: [] },
    ])
    setDraft('')
    setBusy(true)

    const patchAssistant = (patch: (message: PanelMessage) => PanelMessage) =>
      setMessages((current) => {
        const next = [...current]
        next[next.length - 1] = patch(next[next.length - 1])
        return next
      })

    void streamChat(history, context, {
      onText: (delta) =>
        patchAssistant((message) => ({ ...message, content: message.content + delta })),
      onToolCall: (name, args) =>
        patchAssistant((message) => ({
          ...message,
          tools: [...(message.tools ?? []), { name, args }],
        })),
      onDone: () => setBusy(false),
      onError: (message) => {
        patchAssistant((current) => ({
          ...current,
          content: current.content || message,
        }))
        setBusy(false)
      },
    })
  }

  return (
    <aside
      className="fixed inset-x-0 bottom-0 z-30 flex h-[55vh] flex-col border-t bg-ink-raised lg:static lg:h-auto lg:w-90 lg:shrink-0 lg:border-t-0 lg:border-l"
      style={{ borderColor: 'var(--bronze-faint)' }}
      aria-label="the Analyst"
      data-testid="copilot-panel"
    >
      <header
        className="flex items-center justify-between border-b px-3 py-2"
        style={{ borderColor: 'var(--bronze-faint)' }}
      >
        <span className="font-display text-base text-bone">The Analyst</span>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="font-mono text-[10px] text-parchment hover:text-bone"
          aria-label="close the Analyst"
        >
          esc ✕
        </button>
      </header>

      {status.data && !status.data.enabled ? (
        <div className="p-4" data-testid="copilot-setup-card">
          <p className="font-body text-sm text-bone">The Analyst is not connected.</p>
          <p className="mt-2 font-body text-xs text-parchment">
            Add <code className="font-mono">ANTHROPIC_API_KEY</code> to{' '}
            <code className="font-mono">.env</code> and restart — everything else works
            without it. Metric data leaves your infrastructure only to the Anthropic API,
            and only when this feature is enabled.
          </p>
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && (
              <div className="space-y-2">
                <p className="font-body text-xs text-parchment">
                  Ask about the dashboard: risk, kills, calibration, dollars.
                </p>
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => send(suggestion)}
                    className="block w-full border px-2 py-1.5 text-left font-body text-xs text-parchment hover:text-bone"
                    style={{ borderColor: 'var(--bronze-faint)' }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index}>
                <p className="font-mono text-[9px] uppercase tracking-wide text-bronze">
                  {message.role === 'user' ? 'you' : 'analyst'}
                </p>
                {message.tools?.map((chip, chipIndex) => (
                  <p
                    key={chipIndex}
                    className="mt-1 font-mono text-[10px]"
                    style={{ color: 'var(--ochre)' }}
                    data-testid="tool-chip"
                  >
                    ⚙ consulting: {chipLabel(chip)}
                  </p>
                ))}
                <p className="mt-1 font-body text-xs whitespace-pre-wrap text-bone">
                  {message.content || (busy && index === messages.length - 1 ? '…' : '')}
                </p>
              </div>
            ))}
          </div>
          <form
            className="flex gap-2 border-t p-2"
            style={{ borderColor: 'var(--bronze-faint)' }}
            onSubmit={(event) => {
              event.preventDefault()
              send(draft)
            }}
          >
            <label className="sr-only" htmlFor="copilot-input">
              Ask the Analyst
            </label>
            <input
              id="copilot-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="min-w-0 flex-1 border bg-ink-well px-2 py-1.5 font-body text-xs text-bone"
              style={{ borderColor: 'var(--bronze-faint)' }}
              autoComplete="off"
              data-testid="copilot-input"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              className="border px-3 py-1.5 font-body text-xs text-bone disabled:opacity-40"
              style={{ borderColor: 'var(--bronze)' }}
            >
              {busy ? '…' : 'Ask'}
            </button>
          </form>
        </>
      )}
    </aside>
  )
}
