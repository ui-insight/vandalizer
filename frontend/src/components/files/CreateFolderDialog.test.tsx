import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CreateFolderDialog } from './CreateFolderDialog'

describe('CreateFolderDialog', () => {
  it('renders with empty input by default', () => {
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('shows default title "New Folder"', () => {
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByText('New Folder')).toBeInTheDocument()
  })

  it('shows custom title when provided', () => {
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={vi.fn()} title="Add Collection" />)
    expect(screen.getByText('Add Collection')).toBeInTheDocument()
  })

  it('calls onSubmit with trimmed folder name', () => {
    const onSubmit = vi.fn()
    render(<CreateFolderDialog onSubmit={onSubmit} onClose={vi.fn()} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '  My Folder  ' } })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    expect(onSubmit).toHaveBeenCalledWith('My Folder')
  })

  it('does not call onSubmit when name is blank', () => {
    const onSubmit = vi.fn()
    render(<CreateFolderDialog onSubmit={onSubmit} onClose={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn()
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={onClose} />)

    fireEvent.keyDown(screen.getByRole('dialog').parentElement!, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('has accessible dialog role and label', () => {
    render(<CreateFolderDialog onSubmit={vi.fn()} onClose={vi.fn()} />)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'create-folder-dialog-title')
  })
})
