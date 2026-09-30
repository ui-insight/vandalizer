import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CreateKBModal } from './CreateKBModal'

describe('Knowledge creation field feedback', () => {
  it('associates duplicate-name feedback with the title and focuses the field', () => {
    const create = vi.fn()
    render(<CreateKBModal onClose={vi.fn()} onCreate={create} existingTitles={['Research policy']} />)
    const title = screen.getByRole('textbox', { name: 'Title' })
    fireEvent.change(title, { target: { value: 'research POLICY' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(create).not.toHaveBeenCalled()
    expect(title).toHaveAttribute('aria-invalid', 'true')
    expect(title).toHaveAccessibleDescription(expect.stringContaining('already exists'))
    expect(title).toHaveFocus()
    fireEvent.change(title, { target: { value: 'New policy' } })
    expect(title).toHaveAttribute('aria-invalid', 'false')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps valid entries editable after a save failure without marking the title invalid', async () => {
    const create = vi.fn().mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce(undefined)
    render(<CreateKBModal onClose={vi.fn()} onCreate={create} />)
    const title = screen.getByRole('textbox', { name: 'Title' })
    const description = screen.getByRole('textbox', { name: 'Description' })
    fireEvent.change(title, { target: { value: 'New policy' } })
    fireEvent.change(description, { target: { value: 'Internal guidance' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your entries are preserved')
    expect(title).toHaveValue('New policy'); expect(description).toHaveValue('Internal guidance')
    expect(title).toHaveAttribute('aria-invalid', 'false'); expect(title).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2))
    expect(create.mock.calls[0]).toEqual(create.mock.calls[1])
  })

  it('keeps a pending creation open when Escape or the backdrop is used', () => {
    const close = vi.fn()
    render(<CreateKBModal onClose={close} onCreate={() => new Promise(() => {})} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: 'New policy' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog').parentElement!)
    expect(close).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Creating...' })).toBeDisabled()
  })
})
