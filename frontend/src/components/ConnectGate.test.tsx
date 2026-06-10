import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test } from 'vitest'
import { useKeyStore } from '../state/keyStore'
import { ConnectGate } from './ConnectGate'

describe('ConnectGate', () => {
  beforeEach(() => {
    useKeyStore.setState({ key: '' })
  })

  test('hints when the key does not look like a Haruspex key', () => {
    render(<ConnectGate />)
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'sk-oops' } })
    expect(screen.getByText(/keys start with hx_/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled()
  })

  test('stores a plausible key on submit', () => {
    render(<ConnectGate />)
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'hx_valid-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(useKeyStore.getState().key).toBe('hx_valid-key')
  })
})
