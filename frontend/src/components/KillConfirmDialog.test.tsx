import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { makeRun } from '../test/helpers'
import { KillConfirmDialog } from './KillConfirmDialog'

describe('KillConfirmDialog', () => {
  test('arms only when the exact run name is typed', () => {
    const onConfirm = vi.fn()
    render(<KillConfirmDialog run={makeRun()} onConfirm={onConfirm} onClose={vi.fn()} />)
    const confirm = screen.getByTestId('confirm-kill')
    expect(confirm).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: 'gpt2-small' } })
    expect(confirm).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/to confirm/), {
      target: { value: 'gpt2-small-bf16' },
    })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledWith(120)
  })

  test('escape closes the dialog', () => {
    const onClose = vi.fn()
    render(<KillConfirmDialog run={makeRun()} onConfirm={vi.fn()} onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  test('shows grace and checkpoint age', () => {
    render(<KillConfirmDialog run={makeRun()} onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText('120s')).toBeInTheDocument()
    expect(screen.getByText(/Last checkpoint:/)).toBeInTheDocument()
  })
})
