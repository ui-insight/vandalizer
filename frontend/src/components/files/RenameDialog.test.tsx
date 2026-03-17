import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RenameDialog } from './RenameDialog'

describe('RenameDialog', () => {
  it('renders with current name pre-filled', () => {
    render(<RenameDialog currentName="my-doc.pdf" onSubmit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('my-doc.pdf')
  })

  it('calls onSubmit with trimmed new name', () => {
    const onSubmit = vi.fn()
    render(<RenameDialog currentName="old.pdf" onSubmit={onSubmit} onClose={vi.fn()} />)

    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '  new-name.pdf  ' } })
    fireEvent.click(screen.getByRole('button', { name: /rename/i }))

    expect(onSubmit).toHaveBeenCalledWith('new-name.pdf')
  })

  it('does not call onSubmit when name is blank', () => {
    const onSubmit = vi.fn()
    render(<RenameDialog currentName="old.pdf" onSubmit={onSubmit} onClose={vi.fn()} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /rename/i }))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn()
    render(<RenameDialog currentName="doc.pdf" onSubmit={vi.fn()} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    render(<RenameDialog currentName="doc.pdf" onSubmit={vi.fn()} onClose={onClose} />)

    fireEvent.keyDown(screen.getByRole('dialog').parentElement!, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('has accessible dialog role and label', () => {
    render(<RenameDialog currentName="doc.pdf" onSubmit={vi.fn()} onClose={vi.fn()} />)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'rename-dialog-title')
    expect(screen.getByRole('heading', { name: 'Rename' })).toBeInTheDocument()
  })
})
