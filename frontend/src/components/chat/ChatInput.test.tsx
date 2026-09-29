import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getModels } from '../../api/config'
import type { ModelInfo } from '../../types/workflow'
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


it('keeps a failed queued draft and exposes the same action to touch users', async () => {
  const send = vi.fn().mockRejectedValueOnce(new Error('Queue unavailable')).mockResolvedValueOnce(undefined)
  render(<ChatInput onSend={send} isStreaming onStop={vi.fn()} />)
  const input = screen.getByRole('textbox', { name: 'Message input' })
  fireEvent.change(input, { target: { value: 'Review the budget first.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Queue message' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Queue unavailable'))
  expect(input).toHaveValue('Review the budget first.')
  expect(screen.getByRole('button', { name: 'Stop response' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Queue message' }))
  await waitFor(() => expect(input).toHaveValue(''))
  expect(send).toHaveBeenCalledTimes(2)
})

it('serializes sends while retaining a new draft typed during a pending submission', async () => {
  let finish!: () => void
  const send = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  render(<ChatInput onSend={send} />)
  const input = screen.getByRole('textbox', { name: 'Message input' })
  fireEvent.change(input, { target: { value: 'First message' } })
  fireEvent.keyDown(input, { key: 'Enter' }); fireEvent.keyDown(input, { key: 'Enter' })
  expect(send).toHaveBeenCalledTimes(1)
  fireEvent.change(input, { target: { value: 'Next message' } })
  await act(async () => finish())
  expect(input).toHaveValue('Next message')
})

it('recovers model-loading failure and supports arrow selection without losing the draft', async () => {
  vi.mocked(getModels).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([
    { tag: 'first', name: 'First model' }, { tag: 'second', name: 'Second model' },
  ] as ModelInfo[])
  const change = vi.fn()
  render(<ChatInput onSend={vi.fn()} selectedModel="first" onModelChange={change} />)
  fireEvent.change(screen.getByRole('textbox', { name: 'Message input' }), { target: { value: 'Keep this draft' } })
  fireEvent.click(screen.getByRole('button', { name: 'Choose chat model: first' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry models' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Retry models' }))
  const first = await screen.findByRole('radio', { name: 'first' })
  fireEvent.keyDown(first, { key: 'ArrowDown' })
  expect(change).toHaveBeenCalledWith('second')
  expect(screen.queryByRole('dialog', { name: 'Choose chat model' })).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Message input' })).toHaveValue('Keep this draft')
})
