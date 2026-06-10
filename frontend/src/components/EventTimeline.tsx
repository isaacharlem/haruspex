// Policy events for one run (or the fleet), newest first.

import { fmtProb, fmtTime, fmtUsd } from '../lib/format'
import type { PolicyEvent } from '../lib/types'

const KIND_COLOR: Record<string, string> = {
  WARN: 'var(--ochre)',
  KILL_ISSUED: 'var(--oxblood)',
  KILL_ACKED: 'var(--oxblood)',
  OVERRIDDEN: 'var(--verdigris)',
}

function eventDetail(event: PolicyEvent): string {
  const snapshot = event.snapshot as {
    forecast?: { p_diverge?: number; p_hit_target?: number }
    signal_value?: number
    rule?: { when?: { signal?: string } }
    ack_timeout?: boolean
  }
  if (event.kind === 'KILL_ACKED') {
    return `${fmtUsd(event.gross_recovered_usd)} gross · ${fmtUsd(event.expected_recovered_usd)} expected`
  }
  if (event.kind === 'OVERRIDDEN') return 'kill cancelled within the grace window'
  const signal = snapshot.rule?.when?.signal
  const value = snapshot.signal_value
  const timeout = snapshot.ack_timeout ? ' · no ack — marked LOST' : ''
  if (signal && value !== undefined) return `${signal} ${fmtProb(value)}${timeout}`
  if (snapshot.forecast?.p_diverge !== undefined) {
    return `P(diverge) ${fmtProb(snapshot.forecast.p_diverge)}${timeout}`
  }
  return event.policy_name ? `policy ${event.policy_name}${timeout}` : `manual${timeout}`
}

export function EventTimeline({ events, showRun = false }: { events: PolicyEvent[]; showRun?: boolean }) {
  if (events.length === 0) {
    return (
      <p className="font-body text-xs text-parchment">
        No policy events yet. They land here when a rule warns or kills.
      </p>
    )
  }
  return (
    <ol className="space-y-2" aria-label="policy events">
      {events.map((event) => (
        <li key={event.id} className="flex items-baseline gap-2 font-mono text-[11px]">
          <span className="shrink-0 text-parchment">{fmtTime(event.created_at)}</span>
          <span className="shrink-0" style={{ color: KIND_COLOR[event.kind] }}>
            {event.kind}
          </span>
          {showRun && <span className="shrink-0 text-bone">{event.run_name}</span>}
          <span className="text-parchment">{eventDetail(event)}</span>
          {event.policy_name && !showRun && (
            <span className="text-bronze">({event.policy_name})</span>
          )}
        </li>
      ))}
    </ol>
  )
}
