import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast, type ToastType } from './ToastContext'

function Trigger({ message, type }: { message: string; type: ToastType }) {
  const { toast } = useToast()
  return <button onClick={() => toast(message, type)}>fire</button>
}

function setup(message: string, type: ToastType) {
  render(
    <ToastProvider>
      <Trigger message={message} type={type} />
    </ToastProvider>,
  )
  fireEvent.click(screen.getByText('fire'))
}

afterEach(() => {
  vi.useRealTimers()
})

describe('ToastContext auto-dismiss', () => {
  it('keeps an error toast on screen past the auto-dismiss window', () => {
    vi.useFakeTimers()
    setup('Website blocked: https://example.com - not on the allowlist', 'error')
    expect(screen.getByRole('alert')).toBeTruthy()

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.queryByRole('alert')).toBeTruthy()
  })

  it('does not dismiss an error when its body is clicked', () => {
    setup('Something went wrong', 'error')

    fireEvent.click(screen.getByText('Something went wrong'))

    expect(screen.queryByRole('alert')).toBeTruthy()
  })

  it('dismisses an error via the close button', () => {
    setup('Something went wrong', 'error')

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss error' }))

    expect(screen.queryByRole('alert')).toBeNull()
  })

  it.each<ToastType>(['success', 'info'])('auto-dismisses a %s toast after 4s', type => {
    vi.useFakeTimers()
    setup('All good', type)
    expect(screen.getByRole('status')).toBeTruthy()

    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('caps stacked toasts, keeping the newest', () => {
    function Many() {
      const { toast } = useToast()
      return (
        <button onClick={() => { for (let i = 1; i <= 8; i++) toast(`err ${i}`, 'error') }}>
          fire
        </button>
      )
    }
    render(<ToastProvider><Many /></ToastProvider>)
    fireEvent.click(screen.getByText('fire'))

    expect(screen.getAllByRole('alert')).toHaveLength(5)
    expect(screen.queryByText('err 3')).toBeNull()
    expect(screen.getByText('err 8')).toBeTruthy()
  })

  it('dismisses a success toast when clicked', () => {
    setup('All good', 'success')

    fireEvent.click(screen.getByText('All good'))

    expect(screen.queryByRole('status')).toBeNull()
  })
})
