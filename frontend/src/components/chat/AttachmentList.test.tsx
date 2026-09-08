import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { AttachmentList } from './AttachmentList'
import type { FileAttachment } from '../../types/chat'

const file = (id: string, filename: string) => ({ id, filename }) as FileAttachment

// The chip row is the single answer to "what is this conversation looking at".
// Before these, knowledge bases lived in their own bars at the other end of the
// window and folders were sent to the backend with nothing on screen at all.
describe('AttachmentList', () => {
  it('renders knowledge bases, folders and documents in one row', () => {
    const { container } = render(
      <AttachmentList
        knowledgeBases={[{ uuid: 'kb-1', title: 'Export Control' }]}
        selectedFolderUuids={['fld-1']}
        selectedFolderNames={{ 'fld-1': 'FY26 Awards' }}
        selectedDocUuids={['doc-1']}
        selectedDocNames={{ 'doc-1': 'Budget.pdf' }}
        fileAttachments={[file('f1', 'report.pdf')]}
      />,
    )
    const row = container.firstElementChild as HTMLElement
    for (const label of ['Export Control', 'FY26 Awards', 'Budget.pdf', 'report.pdf']) {
      expect(within(row).getByText(label)).toBeInTheDocument()
    }
  })

  it('shows a folder that scopes the chat', () => {
    render(
      <AttachmentList
        selectedFolderUuids={['fld-1']}
        selectedFolderNames={{ 'fld-1': 'FY26 Awards' }}
        onDeselectFolder={() => {}}
      />,
    )
    expect(screen.getByText('FY26 Awards')).toBeInTheDocument()
    expect(screen.getByLabelText('Deselect folder: FY26 Awards')).toBeInTheDocument()
  })

  it('falls back to a generic folder name when the title is unknown', () => {
    render(<AttachmentList selectedFolderUuids={['fld-1']} />)
    expect(screen.getByText('Untitled folder')).toBeInTheDocument()
  })

  it('detaches and shares a knowledge base from its chip', () => {
    const onDetachKB = vi.fn()
    const onShareKB = vi.fn()
    render(
      <AttachmentList
        knowledgeBases={[{ uuid: 'kb-1', title: 'Export Control' }]}
        onDetachKB={onDetachKB}
        onShareKB={onShareKB}
      />,
    )
    fireEvent.click(screen.getByLabelText('Copy share link for knowledge base: Export Control'))
    expect(onShareKB).toHaveBeenCalledWith({ uuid: 'kb-1', title: 'Export Control' })
    fireEvent.click(screen.getByLabelText('Detach knowledge base: Export Control'))
    expect(onDetachKB).toHaveBeenCalledWith('kb-1')
  })

  // Type must survive a colourblind reader and a re-themed --highlight-color,
  // so it is carried by a visible tag, not by the tint alone.
  it('labels the type of scope chips in text', () => {
    render(
      <AttachmentList
        knowledgeBases={[{ uuid: 'kb-1', title: 'Export Control' }]}
        selectedFolderUuids={['fld-1']}
        selectedFolderNames={{ 'fld-1': 'FY26 Awards' }}
      />,
    )
    expect(screen.getByText('KB')).toBeInTheDocument()
    expect(screen.getByText('Folder')).toBeInTheDocument()
  })

  it('collapses a long document selection but keeps the scope chips visible', () => {
    const docUuids = Array.from({ length: 20 }, (_, i) => `doc-${i}`)
    const docNames = Object.fromEntries(docUuids.map((u, i) => [u, `Document ${i}.pdf`]))
    render(
      <AttachmentList
        knowledgeBases={[{ uuid: 'kb-1', title: 'Export Control' }]}
        selectedDocUuids={docUuids}
        selectedDocNames={docNames}
      />,
    )
    // The knowledge base is not pushed out of view by 20 documents.
    expect(screen.getByText('Export Control')).toBeInTheDocument()
    expect(screen.getByText('Document 0.pdf')).toBeInTheDocument()
    expect(screen.queryByText('Document 19.pdf')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '+14 more' }))
    expect(screen.getByText('Document 19.pdf')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Show fewer' }))
    expect(screen.queryByText('Document 19.pdf')).not.toBeInTheDocument()
  })

  it('renders nothing when the conversation has no context', () => {
    const { container } = render(<AttachmentList selectedDocUuids={[]} fileAttachments={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
