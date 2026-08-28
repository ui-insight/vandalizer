import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FixedDocumentsZone } from './FixedDocumentsZone'
import { uploadFile } from '../../api/files'

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedDocUuids: [], selectedDocNames: {} }),
}))
const mockToast = vi.fn()
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: mockToast }) }))
vi.mock('../../api/files', () => ({ uploadFile: vi.fn() }))
vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn(async () => ({ items: [] })) }))
vi.mock('../shared/DocumentPickerDialog', () => ({
  DocumentPickerDialog: ({ title }: { title?: string }) => <div role="dialog">{title}</div>,
}))

const mockUpload = vi.mocked(uploadFile)

// Support ticket: the only click target opened the Vandalizer library picker
// with nothing saying so, and there was no way to bring in a file from the
// user's own machine except an unadvertised drag-drop.
describe('FixedDocumentsZone', () => {
  beforeEach(() => {
    mockToast.mockReset()
    mockUpload.mockReset()
  })

  it('offers both sources by name and opens the library picker labelled as Vandalizer', () => {
    render(<FixedDocumentsZone fixedDocs={[]} onAddDocs={vi.fn()} onRemoveDoc={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Choose from Vandalizer/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Upload from your computer/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Choose from Vandalizer/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Choose from your Vandalizer documents')
  })

  it('uploads a local file, pins the new document, and says so', async () => {
    mockUpload.mockResolvedValue({ complete: true, uuid: 'doc-new' })
    const onAddDocs = vi.fn()
    render(<FixedDocumentsZone fixedDocs={[]} onAddDocs={onAddDocs} onRemoveDoc={vi.fn()} />)

    const input = screen.getByLabelText('Upload files from your computer') as HTMLInputElement
    const file = new File(['hello'], 'budget.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => expect(onAddDocs).toHaveBeenCalledWith([{ uuid: 'doc-new', title: 'budget.pdf' }]))
    expect(mockUpload).toHaveBeenCalledWith(expect.objectContaining({ fileName: 'budget.pdf', extension: 'pdf' }))
    expect(mockToast).toHaveBeenCalledWith('Uploaded budget.pdf', 'success')
  })

  it('reports an upload failure instead of swallowing it', async () => {
    mockUpload.mockRejectedValue(new Error('file too large'))
    const onAddDocs = vi.fn()
    render(<FixedDocumentsZone fixedDocs={[]} onAddDocs={onAddDocs} onRemoveDoc={vi.fn()} />)

    const input = screen.getByLabelText('Upload files from your computer')
    fireEvent.change(input, { target: { files: [new File(['x'], 'big.pdf')] } })

    await waitFor(() => expect(mockToast).toHaveBeenCalledWith('Could not upload big.pdf: file too large', 'error'))
    expect(onAddDocs).not.toHaveBeenCalled()
  })

  // A fixed document deleted from Files (server sets `missing`) is flagged in
  // place and stays removable so the user can clear the failing pin.
  it('flags a deleted fixed document and keeps its remove button', () => {
    const onRemoveDoc = vi.fn()
    render(<FixedDocumentsZone fixedDocs={[{ uuid: 'gone', title: 'Old.pdf', missing: true }]} onAddDocs={vi.fn()} onRemoveDoc={onRemoveDoc} />)
    expect(screen.getByRole('status')).toHaveTextContent('Deleted from Files')
    fireEvent.click(screen.getByLabelText('Remove deleted document Old.pdf'))
    expect(onRemoveDoc).toHaveBeenCalledWith('gone')
  })

  it('hides every way in on a view-only workflow', () => {
    render(<FixedDocumentsZone fixedDocs={[{ uuid: 'a', title: 'Policy.pdf' }]} onAddDocs={vi.fn()} onRemoveDoc={vi.fn()} readOnly />)
    expect(screen.getByText('Policy.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Choose from Vandalizer/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Upload from your computer/ })).not.toBeInTheDocument()
    expect(screen.queryByTestId('fixed-docs-dropzone')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Remove Policy.pdf')).not.toBeInTheDocument()
  })
})
