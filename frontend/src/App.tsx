import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ConnectGate } from './components/ConnectGate'
import { CalibrationPage } from './pages/CalibrationPage'
import { FleetPage } from './pages/FleetPage'
import { KeysPage } from './pages/KeysPage'
import { LedgerPage } from './pages/LedgerPage'
import { PoliciesPage } from './pages/PoliciesPage'
import { RunDetailPage } from './pages/RunDetailPage'
import { useKeyStore } from './state/keyStore'

export default function App() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false },
        },
      }),
  )
  const key = useKeyStore((state) => state.key)

  if (!key) return <ConnectGate />

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<FleetPage />} />
            <Route path="runs/:id" element={<RunDetailPage />} />
            <Route path="policies" element={<PoliciesPage />} />
            <Route path="calibration" element={<CalibrationPage />} />
            <Route path="ledger" element={<LedgerPage />} />
            <Route path="settings/keys" element={<KeysPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
