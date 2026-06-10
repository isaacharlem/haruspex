// Fetch-based SSE client. EventSource cannot send Authorization headers, so
// the stream is read manually with automatic reconnect + backoff.

import type { StreamEvent } from './types'

export interface StreamHandle {
  close: () => void
}

const RECONNECT_BASE_MS = 1000
const RECONNECT_CAP_MS = 15000

export function parseSseChunk(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = []
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    let type = ''
    let data = ''
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue
      if (line.startsWith('event:')) type = line.slice(6).trim()
      else if (line.startsWith('data:')) data += line.slice(5).trim()
    }
    if (type && data) {
      try {
        events.push({ type, data: JSON.parse(data) } as StreamEvent)
      } catch {
        // malformed payload; skip the event
      }
    }
  }
  return { events, rest }
}

export function openStream(
  apiKey: string,
  onEvent: (event: StreamEvent) => void,
  onStateChange?: (connected: boolean) => void,
): StreamHandle {
  let closed = false
  let attempt = 0
  let controller: AbortController | null = null

  async function connect(): Promise<void> {
    while (!closed) {
      controller = new AbortController()
      try {
        const response = await fetch('/v1/stream', {
          headers: { Authorization: `Bearer ${apiKey}` },
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`stream connect failed: ${response.status}`)
        }
        onStateChange?.(true)
        attempt = 0
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const { events, rest } = parseSseChunk(buffer)
          buffer = rest
          for (const event of events) onEvent(event)
        }
      } catch {
        // fall through to reconnect
      }
      onStateChange?.(false)
      if (closed) return
      const delay = Math.min(RECONNECT_CAP_MS, RECONNECT_BASE_MS * 2 ** attempt)
      attempt += 1
      await new Promise((resolve) => setTimeout(resolve, delay))
    }
  }

  void connect()
  return {
    close: () => {
      closed = true
      controller?.abort()
    },
  }
}
