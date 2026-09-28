import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AddUrlsModal } from './AddUrlsModal'

// A double-clicked Add button used to fire two POSTs, enqueueing two ingest
// runs that raced each other and ingested the same URL twice (duplicate-
// source support ticket). Submit must latch after the first click.
describe('AddUrlsModal', () => {
  it('fires onSubmit only once for a rapid double-click', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
      target: { value: 'https://example.com/a\nhttps://example.com/b' },
    })
    const button = screen.getByRole('button', { name: 'Add URLs' })
    fireEvent.click(button)
    fireEvent.click(button)

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith(
      ['https://example.com/a', 'https://example.com/b'],
      false,
      5,
      '',
    )
  })

  it('disables the button and shows progress after submitting', () => {
    render(<AddUrlsModal onSubmit={vi.fn()} onClose={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('URLs to add, one per line'), {
      target: { value: 'https://example.com/a' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))

    const button = screen.getByRole('button', { name: 'Adding…' })
    expect(button).toBeDisabled()
  })

  it('does not submit with no URLs entered', () => {
    const onSubmit = vi.fn()
    render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Add URLs' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })
})


it('retains URLs and crawl settings on failure and retries exactly that draft', async () => {
  const onSubmit = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(undefined)
  const onClose = vi.fn()
  render(<AddUrlsModal onSubmit={onSubmit} onClose={onClose} />)
  fireEvent.change(screen.getByLabelText('URLs to add, one per line'), { target: { value: 'https://example.org/policy' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Enable crawling' }))
  fireEvent.change(screen.getByLabelText('Max pages'), { target: { value: '7' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Your URLs and settings are preserved')
  expect(onClose).not.toHaveBeenCalled()
  expect(screen.getByLabelText('URLs to add, one per line')).toHaveValue('https://example.org/policy')
  fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  expect(onSubmit.mock.calls[0]).toEqual(onSubmit.mock.calls[1])
})

it('identifies an invalid URL line before submitting', () => {
  const onSubmit = vi.fn()
  render(<AddUrlsModal onSubmit={onSubmit} onClose={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('URLs to add, one per line'), { target: { value: 'https://example.org/good\nnot a URL' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add URLs' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Line 2')
  expect(onSubmit).not.toHaveBeenCalled()
})
