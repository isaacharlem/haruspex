// UI-only state: toasts, the Analyst dock, stream connectivity.

import { create } from 'zustand'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'warn' | 'kill'
}

interface UiState {
  toasts: Toast[]
  copilotOpen: boolean
  streamConnected: boolean
  pushToast: (message: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
  setCopilotOpen: (open: boolean) => void
  setStreamConnected: (connected: boolean) => void
}

let nextToastId = 1

export const useUiStore = create<UiState>((set) => ({
  toasts: [],
  copilotOpen: false,
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
  setStreamConnected: (connected) => set({ streamConnected: connected }),
}))
