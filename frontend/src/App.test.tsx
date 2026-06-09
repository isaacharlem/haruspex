import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import App from './App'

test('renders the Haruspex shell', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'Haruspex' })).toBeInTheDocument()
})
