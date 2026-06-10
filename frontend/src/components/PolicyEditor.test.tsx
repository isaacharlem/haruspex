import { fireEvent, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { KILL_DOOMED_TEMPLATE } from '../lib/policyTemplates'
import { mockFetch, renderWithProviders } from '../test/helpers'
import { PolicyEditor } from './PolicyEditor'

beforeEach(() => {
  mockFetch({})
})

function renderEditor(onSave = vi.fn()) {
  renderWithProviders(
    <PolicyEditor initial={KILL_DOOMED_TEMPLATE} onSave={onSave} saving={false} serverError={null} />,
  )
  return onSave
}

describe('PolicyEditor validation', () => {
  test('template is valid and saveable', () => {
    const onSave = renderEditor()
    fireEvent.click(screen.getByTestId('save-policy'))
    expect(onSave).toHaveBeenCalledWith(KILL_DOOMED_TEMPLATE)
  })

  test('empty name blocks saving with a message', () => {
    const onSave = renderEditor()
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: '' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Name the policy.')
    expect(screen.getByTestId('save-policy')).toBeDisabled()
    expect(onSave).not.toHaveBeenCalled()
  })

  test('bad signal is rejected', () => {
    renderEditor()
    fireEvent.change(screen.getByLabelText(/Signal/), { target: { value: 'p_doom' } })
    expect(screen.getByRole('alert')).toHaveTextContent(/Signal must be one of/)
  })

  test('raw JSON mode surfaces syntax errors and recovers', () => {
    renderEditor()
    fireEvent.click(screen.getByRole('button', { name: 'raw JSON' }))
    const textarea = screen.getByLabelText('policy definition JSON')
    fireEvent.change(textarea, { target: { value: '{not json' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid JSON')
    fireEvent.change(textarea, { target: { value: JSON.stringify(KILL_DOOMED_TEMPLATE) } })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('server errors render when local validation passes', () => {
    renderWithProviders(
      <PolicyEditor
        initial={KILL_DOOMED_TEMPLATE}
        onSave={vi.fn()}
        saving={false}
        serverError="policy named 'x' already exists"
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('already exists')
  })

  test('form edits round-trip into the JSON view', () => {
    renderEditor()
    fireEvent.change(screen.getByLabelText(/Threshold/), { target: { value: '0.10' } })
    fireEvent.click(screen.getByRole('button', { name: 'raw JSON' }))
    const textarea = screen.getByLabelText('policy definition JSON') as HTMLTextAreaElement
    expect(JSON.parse(textarea.value).when.value).toBe(0.1)
  })
})
