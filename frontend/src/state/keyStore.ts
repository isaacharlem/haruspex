// The dashboard's own API key: entered once, kept in localStorage.

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { setApiKey } from '../lib/api'

interface KeyState {
  key: string
  setKey: (key: string) => void
  clearKey: () => void
}

export const useKeyStore = create<KeyState>()(
  persist(
    (set) => ({
      key: '',
      setKey: (key: string) => {
        setApiKey(key)
        set({ key })
      },
      clearKey: () => {
        setApiKey('')
        set({ key: '' })
      },
    }),
    {
      name: 'haruspex-dashboard-key',
      onRehydrateStorage: () => (state) => {
        if (state?.key) setApiKey(state.key)
      },
    },
  ),
)
