// Streaming chat with the Analyst: POST + SSE parse with live callbacks.

import { getApiKey } from './api'
import { parseSseChunk } from './sse'

export interface ChatTurnMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatCallbacks {
  onText: (text: string) => void
  onToolCall: (name: string, args: Record<string, unknown>) => void
  onDone: (stopReason: string) => void
  onError: (message: string) => void
}

export async function streamChat(
  messages: ChatTurnMessage[],
  context: Record<string, unknown>,
  callbacks: ChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch('/v1/copilot/chat', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getApiKey()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ messages, context }),
      signal,
    })
  } catch {
    callbacks.onError('The Analyst is unreachable. Check the API connection.')
    return
  }

  if (!response.ok || !response.body) {
    let message = `The Analyst returned status ${response.status}.`
    try {
      const body = (await response.json()) as { error?: { message: string } }
      if (body.error) message = body.error.message
    } catch {
      // keep the generic message
    }
    callbacks.onError(message)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { events, rest } = parseSseChunk(buffer)
    buffer = rest
    for (const event of events) {
      const data = event.data as Record<string, unknown>
      if (event.type === ('text_delta' as never)) callbacks.onText(String(data.text ?? ''))
      else if (event.type === ('tool_call' as never))
        callbacks.onToolCall(String(data.name ?? ''), (data.args ?? {}) as Record<string, unknown>)
      else if (event.type === ('done' as never)) callbacks.onDone(String(data.stop_reason ?? ''))
      else if (event.type === ('error' as never)) callbacks.onError(String(data.message ?? ''))
    }
  }
}
