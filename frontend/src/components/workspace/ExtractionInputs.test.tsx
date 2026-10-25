import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ExtractionInputs } from './ExtractionInputs'
import { searchDocuments } from '../../api/documents'

vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
const documents = [{ uuid: 'doc-1', title: 'Proposal.pdf' }, { uuid: 'doc-2', title: 'Budget.pdf' }]
const props = { documents, usesProjectFiles: false, combined: false, onCombinedChange: vi.fn(), onAdd: vi.fn(), onRemove: vi.fn() }

describe('extraction input selection', () => {
  it('excludes existing inputs and cancels a pending selection without changing the run scope', async () => {
    vi.mocked(searchDocuments).mockResolvedValue({ items: [...documents, { uuid: 'doc-3', title: 'Award.pdf' }], total: 3 } as Awaited<ReturnType<typeof searchDocuments>>)
    const add = vi.fn()
    const view = render(<ExtractionInputs {...props} onAdd={add} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add documents' }))
    const dialog = screen.getByRole('dialog', { name: 'Choose extraction documents' })
    expect(view.container.contains(dialog)).toBe(false)
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Award.pdf' }))
    expect(screen.queryByRole('checkbox', { name: 'Proposal.pdf' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(add).not.toHaveBeenCalled()
    expect(screen.getByText('2 selected')).toBeVisible()
  })

  it('adds only the newly confirmed documents', async () => {
    vi.mocked(searchDocuments).mockResolvedValue({ items: [{ uuid: 'doc-3', title: 'Award.pdf' }], total: 1 } as Awaited<ReturnType<typeof searchDocuments>>)
    const add = vi.fn()
    render(<ExtractionInputs {...props} onAdd={add} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add documents' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Award.pdf' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 Selected' }))
    expect(add).toHaveBeenCalledWith([{ uuid: 'doc-3', title: 'Award.pdf' }])
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('distinguishes per-document results, combined input and the project fallback', () => {
    const change = vi.fn(), remove = vi.fn()
    const view = render(<ExtractionInputs {...props} onCombinedChange={change} onRemove={remove} usesProjectFiles />)
    expect(screen.getByText('Off: a separate result for each document.')).toBeVisible()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(change).toHaveBeenCalledWith(true)
    fireEvent.click(screen.getByText('Review 2 selected documents'))
    fireEvent.click(screen.getByRole('button', { name: 'Remove Budget.pdf from extraction' }))
    expect(remove).toHaveBeenCalledWith('doc-2')
    expect(screen.getByText('Removing all selections uses all project files.')).toBeVisible()
    view.rerender(<ExtractionInputs {...props} documents={[]} usesProjectFiles />)
    expect(screen.getByText('All project files will be used')).toBeVisible()
    expect(screen.queryByRole('checkbox')).toBeNull()
  })
})
