// The Analyst: a dockable chat panel that talks through the dashboard.
// Desktop: a sticky right dock with a draggable edge (320–640px, persisted).
// Small screens: a bottom sheet. Without a server key it renders a setup
// card — everything else works without it.

import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useCopilotStatus } from '../hooks/queries'
import { streamChat, type ChatTurnMessage } from '../lib/copilotStream'
import { COPILOT_DEFAULT_WIDTH, useUiStore } from '../state/uiStore'

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
  const width = useUiStore((state) => state.copilotWidth)
  const setWidth = useUiStore((state) => state.setCopilotWidth)
  const status = useCopilotStatus()
  const location = useLocation()
  const [messages, setMessages] = useState<PanelMessage[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)

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
        className="tablet tablet-link fixed right-4 bottom-16 z-30 px-3.5 py-2 font-body text-xs text-bone sm:bottom-4"
        data-testid="open-copilot"
      >
        <span aria-hidden="true" className="mr-1.5 text-bronze">
          ✦
        </span>
        Analyst
      </button>
    )
  }

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const onResize = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
    const right = panelRef.current?.getBoundingClientRect().right ?? window.innerWidth
    setWidth(right - event.clientX)
  }
  const onResizeKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowLeft') setWidth(width + 24)
    else if (event.key === 'ArrowRight') setWidth(width - 24)
    else if (event.key === 'Home') setWidth(COPILOT_DEFAULT_WIDTH)
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
      ref={panelRef}
      className="fixed inset-x-0 bottom-0 z-30 flex h-[60vh] flex-col border-t bg-ink-raised lg:sticky lg:top-0 lg:h-screen lg:shrink-0 lg:border-t-0 lg:border-l lg:[width:var(--copilot-w)]"
      style={
        {
          borderColor: 'var(--bronze-faint)',
          '--copilot-w': `${width}px`,
        } as React.CSSProperties
      }
      aria-label="the Analyst"
      data-testid="copilot-panel"
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="resize the Analyst panel (arrow keys; Home resets)"
        tabIndex={0}
        onPointerDown={startResize}
        onPointerMove={onResize}
        onKeyDown={onResizeKey}
        data-testid="copilot-resize"
        className="group absolute top-0 bottom-0 left-0 z-10 hidden w-2 cursor-col-resize touch-none lg:block"
      >
        <span
          aria-hidden="true"
          className="absolute top-0 bottom-0 left-0 w-px bg-transparent transition-colors group-hover:bg-bronze group-focus-visible:bg-bronze"
        />
      </div>

      <header
        className="flex items-center justify-between border-b px-3.5 py-2.5"
        style={{
          borderColor: 'var(--bronze-faint)',
          background: 'linear-gradient(160deg, rgba(138,111,63,0.08), transparent 60%)',
        }}
      >
        <span className="font-display text-base text-bone">
          <span aria-hidden="true" className="mr-1.5 text-bronze">
            ✦
          </span>
          The Analyst
        </span>
        <span className="flex items-center gap-3">
          {status.data?.enabled && (
            <span className="font-mono text-[9px] text-parchment">{status.data.model}</span>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="font-mono text-[10px] text-parchment transition-colors hover:text-bone"
            aria-label="close the Analyst"
          >
            esc ✕
          </button>
        </span>
      </header>

      {status.data && !status.data.enabled ? (
        <div className="p-4" data-testid="copilot-setup-card">
          <div className="tablet p-4">
            <p className="font-body text-sm text-bone">The Analyst is not connected.</p>
            <p className="mt-2 font-body text-xs leading-relaxed text-parchment">
              Add <code className="font-mono">ANTHROPIC_API_KEY</code> to{' '}
              <code className="font-mono">.env</code> and restart — everything else works
              without it. Metric data leaves your infrastructure only to the Anthropic API,
              and only when this feature is enabled.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3.5">
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
                    className="tablet tablet-link block w-full px-3 py-2 text-left font-body text-xs text-parchment hover:text-bone"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className="fade-up">
                <p className="rune-rule font-mono text-[9px] tracking-[0.14em] text-bronze uppercase">
                  {message.role === 'user' ? 'you' : 'analyst'}
                </p>
                {message.tools?.map((chip, chipIndex) => (
                  <p
                    key={chipIndex}
                    className="mt-1.5 truncate font-mono text-[10px]"
                    style={{ color: 'var(--ochre)' }}
                    title={chipLabel(chip)}
                    data-testid="tool-chip"
                  >
                    ⚙ consulting: {chipLabel(chip)}
                  </p>
                ))}
                <p className="mt-1.5 font-body text-xs leading-relaxed break-words whitespace-pre-wrap text-bone">
                  {message.content ||
                    (busy && index === messages.length - 1 ? (
                      <span className="augur-shimmer">divining…</span>
                    ) : (
                      ''
                    ))}
                </p>
              </div>
            ))}
          </div>
          <form
            className="flex gap-2 border-t p-2.5"
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
              className="min-w-0 flex-1 border bg-ink-well px-2.5 py-1.5 font-body text-xs text-bone transition-colors hover:border-bronze"
              style={{ borderColor: 'var(--bronze-faint)' }}
              autoComplete="off"
              data-testid="copilot-input"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              className="border px-3.5 py-1.5 font-body text-xs text-bone transition-colors hover:bg-ink-well disabled:opacity-40"
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
