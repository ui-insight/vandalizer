import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ImportTestQueriesModal } from './ImportTestQueriesModal'
import { importKBTestQueries } from '../../api/knowledge'

vi.mock('../../api/knowledge', () => ({ importKBTestQueries: vi.fn() }))
const result = { created: 1, updated: 0, skipped: 0, total_rows: 2, errors: [{ row: 3, error: 'Question is blank' }] }
function setup() {
  const onClose = vi.fn(), onImported = vi.fn()
  const view = render(<ImportTestQueriesModal kbUuid="kb-1" onClose={onClose} onImported={onImported} />)
  const pick = (file: File) => fireEvent.change(view.container.querySelector('input[type=file]')!, { target: { files: [file] } })
  return { pick, onClose, onImported }
}
describe('question import recovery', () => {
  it('validates the supported extension and server size limit before upload', () => {
    const { pick } = setup()
    pick(new File(['text'], 'questions.txt'))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a CSV or Excel')
    const large = new File(['x'], 'questions.csv')
    Object.defineProperty(large, 'size', { value: 5 * 1024 * 1024 + 1 })
    pick(large)
    expect(screen.getByRole('alert')).toHaveTextContent('5 MB limit')
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('preserves the file for retry and reports partial success without offering duplicate import', async () => {
    vi.mocked(importKBTestQueries).mockRejectedValueOnce(new Error('Service unavailable')).mockResolvedValueOnce(result)
    const { pick, onImported } = setup()
    pick(new File(['Question\nExample'], 'questions.csv'))
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable')
    expect(screen.getByText('questions.csv')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 created')
    expect(screen.getByRole('status')).toHaveTextContent('Row 3: Question is blank')
    expect(screen.getByRole('button', { name: 'Import complete' })).toBeDisabled()
    expect(onImported).toHaveBeenCalledOnce()
  })

  it('locks file replacement and closing while the import is pending', async () => {
    let resolveImport!: (value: typeof result) => void
    vi.mocked(importKBTestQueries).mockImplementationOnce(() => new Promise(resolve => { resolveImport = resolve }))
    const { pick, onClose } = setup()
    pick(new File(['Question\nExample'], 'first.csv'))
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    pick(new File(['Question\nOther'], 'second.csv'))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByText('first.csv')).toBeInTheDocument()
    resolveImport(result)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Done' })).toBeEnabled())
  })
})
