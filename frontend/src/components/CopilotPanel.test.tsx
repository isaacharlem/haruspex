import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { mockFetch, renderWithProviders } from '../test/helpers'
import { useUiStore } from '../state/uiStore'
import { CopilotPanel } from './CopilotPanel'

function sseResponse(frames: string): Response {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(frames))
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

describe('CopilotPanel', () => {
  beforeEach(() => {
    useUiStore.setState({ copilotOpen: true })
  })

  test('renders the setup card when the server has no key', async () => {
    mockFetch({ '/copilot/status': { enabled: false, model: null } })
    renderWithProviders(<CopilotPanel />)
    await waitFor(() => expect(screen.getByTestId('copilot-setup-card')).toBeInTheDocument())
    expect(screen.getByText('ANTHROPIC_API_KEY')).toBeInTheDocument()
    expect(screen.getByText(/everything else works/)).toBeInTheDocument()
    expect(screen.queryByTestId('copilot-input')).not.toBeInTheDocument()
  })

  test('renders the chat box with suggestions when enabled', async () => {
    mockFetch({ '/copilot/status': { enabled: true, model: 'claude-sonnet-4-6' } })
    renderWithProviders(<CopilotPanel />)
    await waitFor(() => expect(screen.getByTestId('copilot-input')).toBeInTheDocument())
    expect(screen.getByText('Which runs are at risk right now and why?')).toBeInTheDocument()
  })

  test('streams an answer with live tool chips', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/copilot/status')) {
        return new Response(JSON.stringify({ enabled: true, model: 'claude-sonnet-4-6' }), {
          status: 200,
        })
      }
      if (url.includes('/copilot/chat')) {
        expect(JSON.parse(String(init?.body)).context.route).toBe('/')
        return sseResponse(
          'event: tool_call\ndata: {"name":"list_runs","args":{"status":"RUNNING"}}\n\n' +
            'event: text_delta\ndata: {"text":"Two runs are "}\n\n' +
            'event: text_delta\ndata: {"text":"at risk."}\n\n' +
            'event: done\ndata: {"stop_reason":"end_turn","iterations":1}\n\n',
        )
      }
      return new Response('{}', { status: 404 })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CopilotPanel />)
    await waitFor(() => expect(screen.getByTestId('copilot-input')).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('copilot-input'), {
      target: { value: 'Which runs are at risk?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(screen.getByText('Two runs are at risk.')).toBeInTheDocument())
    expect(screen.getByTestId('tool-chip')).toHaveTextContent(
      'consulting: list_runs(status: RUNNING)',
    )
  })

  test('surfaces stream errors in the transcript', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/copilot/status')) {
        return new Response(JSON.stringify({ enabled: true, model: 'm' }), { status: 200 })
      }
      return new Response(
        JSON.stringify({ error: { code: 'conflict', message: 'The Analyst is disabled', request_id: 't' } }),
        { status: 409 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    renderWithProviders(<CopilotPanel />)
    await waitFor(() => expect(screen.getByTestId('copilot-input')).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('copilot-input'), { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(screen.getByText('The Analyst is disabled')).toBeInTheDocument())
  })

  test('collapsed state shows the opener button', () => {
    useUiStore.setState({ copilotOpen: false })
    mockFetch({ '/copilot/status': { enabled: true, model: 'm' } })
    renderWithProviders(<CopilotPanel />)
    expect(screen.getByTestId('open-copilot')).toBeInTheDocument()
  })
})
