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


it('keeps typing and the draft while transfer blocks Enter and Send', () => {
  const onSend = vi.fn()
  const view = render(<ChatInput onSend={onSend} sendDisabled />)
  const input = screen.getByRole('textbox', { name: 'Message input' })
  fireEvent.change(input, { target: { value: 'Use the uploaded document.' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onSend).not.toHaveBeenCalled()
  expect(input).toHaveValue('Use the uploaded document.')
  expect(input).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
  view.rerender(<ChatInput onSend={onSend} />)
  fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
  expect(onSend).not.toHaveBeenCalled()
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onSend).toHaveBeenCalledExactlyOnceWith('Use the uploaded document.')
})


it('does not send Enter used to confirm composed text', () => {
  const onSend = vi.fn()
  render(<ChatInput onSend={onSend} />)
  const input = screen.getByRole('textbox', { name: 'Message input' })
  fireEvent.change(input, { target: { value: 'Check this text' } })
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  expect(onSend).not.toHaveBeenCalled()
  expect(input).toHaveValue('Check this text')
})
