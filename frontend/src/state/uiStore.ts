// UI-only state: toasts, the Analyst dock (open state + width), stream
// connectivity. Panel width persists across visits via localStorage.

import { create } from 'zustand'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'warn' | 'kill'
}

export const COPILOT_MIN_WIDTH = 320
export const COPILOT_MAX_WIDTH = 640
export const COPILOT_DEFAULT_WIDTH = 392

const WIDTH_STORAGE_KEY = 'haruspex-copilot-width'

function clampWidth(width: number): number {
  return Math.min(COPILOT_MAX_WIDTH, Math.max(COPILOT_MIN_WIDTH, Math.round(width)))
}

function initialWidth(): number {
  try {
    const stored = window.localStorage.getItem(WIDTH_STORAGE_KEY)
    if (stored) return clampWidth(Number(stored))
  } catch {
    // private mode / SSR — fall through to default
  }
  return COPILOT_DEFAULT_WIDTH
}

interface UiState {
  toasts: Toast[]
  copilotOpen: boolean
  copilotWidth: number
  streamConnected: boolean
  pushToast: (message: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
  setCopilotOpen: (open: boolean) => void
  setCopilotWidth: (width: number) => void
  setStreamConnected: (connected: boolean) => void
}

let nextToastId = 1

export const useUiStore = create<UiState>((set) => ({
  toasts: [],
  copilotOpen: false,
  copilotWidth: initialWidth(),
  streamConnected: false,
  pushToast: (message, tone = 'info') => {
    const id = nextToastId++
    set((state) => ({ toasts: [...state.toasts.slice(-3), { id, message, tone }] }))
    // Kill notifications stay until dismissed; routine toasts fade.
    if (tone !== 'kill') {
      setTimeout(() => {
        set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
      }, 6000)
    }
  },
  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
  setCopilotOpen: (open) => set({ copilotOpen: open }),
  setCopilotWidth: (width) => {
    const clamped = clampWidth(width)
    try {
      window.localStorage.setItem(WIDTH_STORAGE_KEY, String(clamped))
    } catch {
      // best-effort persistence only
    }
    set({ copilotWidth: clamped })
  },
  setStreamConnected: (connected) => set({ streamConnected: connected }),
}))
