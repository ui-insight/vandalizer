import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DocumentPickerModal } from './DocumentPickerModal'
import { searchDocuments } from '../../api/documents'
vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
vi.mock('../../api/folders', () => ({ listAllFolders: vi.fn().mockResolvedValue([{ uuid: 'folder', title: 'Research', path: 'Research' }]) }))
vi.mock('../../api/files', () => ({ uploadFile: vi.fn(), getUploadPolicy: vi.fn().mockResolvedValue({ extensions: ['txt'], max_size_bytes: 1024 }) }))
const documents = [{ uuid: 'doc-1', title: 'Policy.txt', extension: 'txt', num_pages: 1, token_count: 50, folder: null }]
beforeEach(() => { vi.mocked(searchDocuments).mockReset().mockResolvedValue({ items: documents, total: 1 } as never) })

describe('document picker recovery', () => {
  it('preserves a selected document after failure and retries the same IDs', async () => {
    const submit = vi.fn().mockRejectedValueOnce(new Error('Add unavailable')).mockResolvedValueOnce(undefined), close = vi.fn()
    render(<DocumentPickerModal onSubmit={submit} onClose={close} />)
    fireEvent.click(await screen.findByRole('button', { name: /Policy.txt/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Add (1)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your selection is preserved')
    expect(screen.getByRole('button', { name: /Policy.txt/ })).toHaveAttribute('aria-pressed', 'true')
    expect(close).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Add (1)' }))
    await waitFor(() => expect(close).toHaveBeenCalledOnce())
    expect(submit.mock.calls).toEqual([[['doc-1']], [['doc-1']]])
  })
  it('holds the dialog and blocks repeat submission while adding', async () => {
    let finish!: () => void
    const submit = vi.fn(() => new Promise<void>(resolve => { finish = resolve })), close = vi.fn()
    render(<DocumentPickerModal onSubmit={submit} onClose={close} />)
    fireEvent.click(await screen.findByRole('button', { name: /Policy.txt/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Add (1)' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Adding…' }))
    expect(submit).toHaveBeenCalledOnce()
    expect(close).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await act(async () => finish())
    expect(close).toHaveBeenCalledOnce()
  })
  it('offers a retry when document search fails', async () => {
    vi.mocked(searchDocuments).mockRejectedValueOnce(new Error('Search unavailable'))
    render(<DocumentPickerModal onSubmit={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Retry search' }))
    expect(await screen.findByRole('button', { name: /Policy.txt/ })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
