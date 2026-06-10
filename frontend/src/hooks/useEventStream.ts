// One SSE subscription for the whole app: patches query caches on
// run.updated / forecast.updated / policy.fired / ledger.updated — no polling.

import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { openStream } from '../lib/sse'
import type { StreamEvent } from '../lib/types'
import { useKeyStore } from '../state/keyStore'
import { useUiStore } from '../state/uiStore'

const INVALIDATE_DEBOUNCE_MS = 800

export function useEventStream(): void {
  const key = useKeyStore((state) => state.key)
  const queryClient = useQueryClient()
  const pushToast = useUiStore((state) => state.pushToast)
  const setStreamConnected = useUiStore((state) => state.setStreamConnected)
  const pending = useRef<Set<string>>(new Set())
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!key) return

    const flush = () => {
      timer.current = null
      const keys = [...pending.current]
      pending.current.clear()
      for (const root of keys) {
        if (root.startsWith('run:')) {
          const id = Number(root.slice(4))
          void queryClient.invalidateQueries({ queryKey: ['run', id] })
          void queryClient.invalidateQueries({ queryKey: ['metrics', id] })
          void queryClient.invalidateQueries({ queryKey: ['forecasts', id] })
        } else {
          void queryClient.invalidateQueries({ queryKey: [root] })
        }
      }
    }

    const schedule = (rootKey: string) => {
      pending.current.add(rootKey)
      timer.current ??= setTimeout(flush, INVALIDATE_DEBOUNCE_MS)
    }

    const onEvent = (event: StreamEvent) => {
      const runId = typeof event.data.run_id === 'number' ? event.data.run_id : null
      switch (event.type) {
        case 'run.updated':
        case 'forecast.updated':
          schedule('runs')
          if (runId !== null) schedule(`run:${runId}`)
          break
        case 'policy.fired': {
          schedule('events')
          schedule('runs')
          if (runId !== null) schedule(`run:${runId}`)
          const kind = String(event.data.kind ?? '')
          if (kind === 'KILL_ISSUED') pushToast(`Kill directed for run ${runId}`, 'kill')
          else if (kind === 'WARN') pushToast(`Policy warning on run ${runId}`, 'warn')
          else if (kind === 'KILL_ACKED') pushToast(`Run ${runId} stopped; dollars on the ledger`, 'info')
          else if (kind === 'OVERRIDDEN') pushToast(`Kill on run ${runId} overridden`, 'info')
          break
        }
        case 'ledger.updated':
          schedule('ledger')
          break
      }
    }

    const handle = openStream(key, onEvent, setStreamConnected)
    return () => {
      handle.close()
      if (timer.current) clearTimeout(timer.current)
    }
  }, [key, queryClient, pushToast, setStreamConnected])
}
