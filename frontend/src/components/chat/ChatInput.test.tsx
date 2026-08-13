import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChatInput } from './ChatInput'

vi.mock('../../api/config', () => ({
  getModels: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../../contexts/BrandingContext', () => ({
  useBranding: () => ({ orgName: 'Vandalizer' }),
}))

describe('ChatInput', () => {
  it('keeps the one-line composer from producing a horizontal scrollbar', () => {
    render(<ChatInput onSend={vi.fn()} />)

    const input = screen.getByRole('textbox', { name: 'Message input' })
    expect(input).toHaveAttribute('wrap', 'soft')
    expect(input).toHaveClass('overflow-x-hidden', 'overflow-y-auto')
    expect(input).toHaveStyle({ minHeight: '24px', lineHeight: '1.5' })

    fireEvent.change(input, { target: { value: 'Check the budget total.' } })
    expect(input).toHaveStyle({ height: '24px' })
  })
})
