import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AddToLibraryDialog } from './AddToLibraryDialog'
import { addItem, listItems } from '../../api/library'
import type { Library, LibraryItem } from '../../types/library'
vi.mock('../../api/library', () => ({ addItem: vi.fn(), listItems: vi.fn() }))
vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => children }))
const libraries = [{ id: 'mine', title: 'My library', scope: 'personal' }] as Library[]
beforeEach(() => { vi.clearAllMocks(); vi.mocked(listItems).mockResolvedValue([]); vi.mocked(addItem).mockResolvedValue({ id: 'saved' } as LibraryItem) })
function setup() { const onClose = vi.fn(), onAdded = vi.fn(), onOpen = vi.fn(); render(<AddToLibraryDialog libraries={libraries} itemId="wf-1" itemName="Review proposal" kind="workflow" onClose={onClose} onAdded={onAdded} onOpen={onOpen} />); return { onClose, onAdded, onOpen } }
describe('catalog saving', () => {
  it('identifies an existing reference and offers opening without writing again', async () => {
    vi.mocked(listItems).mockResolvedValue([{ item_id: 'wf-1', kind: 'workflow' } as LibraryItem])
    const { onOpen } = setup()
    expect(await screen.findByText('Already saved in My library.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Open workflow' }))
    expect(onOpen).toHaveBeenCalledOnce(); expect(addItem).not.toHaveBeenCalled()
  })
  it('retains destination on failure and shows a durable success after retry', async () => {
    vi.mocked(addItem).mockRejectedValueOnce(new Error('Offline'))
    const { onAdded, onClose } = setup()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
    expect(screen.getByLabelText('Destination library')).toHaveValue('mine')
    fireEvent.click(screen.getByRole('button', { name: 'Retry save' }))
    expect(await screen.findByText('Saved to My library.')).toBeVisible()
    expect(onAdded).toHaveBeenCalledWith(libraries[0]); expect(onClose).not.toHaveBeenCalled()
  })
  it('blocks repeated saves and dismissal while the request is pending', async () => {
    let resolve!: (item: LibraryItem) => void
    vi.mocked(addItem).mockImplementation(() => new Promise(done => { resolve = done }))
    const { onClose } = setup()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled())
    const save = screen.getByRole('button', { name: 'Save' })
    fireEvent.click(save); fireEvent.click(save); fireEvent.keyDown(document, { key: 'Escape' })
    expect(addItem).toHaveBeenCalledOnce(); expect(onClose).not.toHaveBeenCalled()
    await act(async () => { resolve({ id: 'saved' } as LibraryItem) })
  })
})
