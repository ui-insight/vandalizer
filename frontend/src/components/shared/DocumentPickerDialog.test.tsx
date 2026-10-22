import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { searchDocuments } from '../../api/documents'
import { DocumentPickerDialog } from './DocumentPickerDialog'
vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
const search = vi.mocked(searchDocuments)
const response = (uuid: string) => ({ items: [{ uuid, title: uuid }], total: 1 }) as Awaited<ReturnType<typeof searchDocuments>>

describe('nested document selection', () => {
  it('preserves choices across searches and retries a failed search', async () => {
    search.mockResolvedValueOnce(response('First')).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(response('Second'))
    const select = vi.fn()
    render(<DocumentPickerDialog excludeUuids={[]} onSelect={select} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('checkbox', { name: 'First' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Search documents' }), { target: { value: 'Second' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Retry search' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Second' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add 2 Selected' }))
    expect(select).toHaveBeenCalledWith([{ uuid: 'First', title: 'First' }, { uuid: 'Second', title: 'Second' }])
  })
  it('does not let stale results replace the latest query and isolates Escape', async () => {
    let resolveOld!: (value: Awaited<ReturnType<typeof searchDocuments>>) => void
    search.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve })).mockResolvedValueOnce(response('Latest'))
    const parent = vi.fn(), close = vi.fn()
    window.addEventListener('keydown', parent)
    render(<DocumentPickerDialog excludeUuids={[]} onSelect={vi.fn()} onClose={close} />)
    await waitFor(() => expect(search).toHaveBeenCalledWith('', 30))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Latest' } })
    await screen.findByRole('checkbox', { name: 'Latest' })
    resolveOld(response('Old'))
    await waitFor(() => expect(screen.queryByRole('checkbox', { name: 'Old' })).not.toBeInTheDocument())
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(close).toHaveBeenCalledTimes(1); expect(parent).not.toHaveBeenCalled()
    window.removeEventListener('keydown', parent)
  })
})
