import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

const workspace = {
  setWorkspaceMode: vi.fn(),
  viewDocument: vi.fn(),
  openDocumentUuid: null as string | null,
}

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}))

vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn() }),
}))

vi.mock('../../api/feedback', () => ({
  submitChatFeedback: vi.fn(),
}))

const CHUNK =
  'Recipients must retain financial records for three years after submission '
  + 'of the final expenditure report, unless the awarding agency directs otherw'

function messageWith(citation: Partial<Citation>): ChatMessageType {
  return {
    role: 'assistant',
    content: 'Records are kept for three years.',
    citations: [{
      document_title: 'Uniform Guidance',
      document_id: 'src-1',
      chunk_id: 'chunk-1',
      page: 12,
      content_preview: CHUNK,
      ...citation,
    }],
  }
}

describe('ChatMessage source citations', () => {
  beforeEach(() => {
    workspace.setWorkspaceMode.mockClear()
    workspace.viewDocument.mockClear()
    workspace.openDocumentUuid = null
  })

  it('offers Preview and Open when the cited document can be opened', () => {
    render(<ChatMessage message={messageWith({ document_uuid: 'doc-1' })} />)

    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))

    expect(screen.getByRole('menuitem', { name: 'Preview' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Open at p. 12' })).toBeTruthy()
    // The chunk text is not shown until Preview is chosen.
    expect(screen.queryByText(/Recipients must retain/)).toBeNull()
  })

  it('Preview shows the chunk text without opening the document', () => {
    render(<ChatMessage message={messageWith({ document_uuid: 'doc-1' })} />)

    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Preview' }))

    expect(screen.getByText(/Recipients must retain/)).toBeTruthy()
    expect(workspace.viewDocument).not.toHaveBeenCalled()
  })

  it('Open sends the viewer to the cited page with a whole-word anchor', () => {
    render(<ChatMessage message={messageWith({ document_uuid: 'doc-1' })} />)

    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Open at p. 12' }))

    expect(workspace.setWorkspaceMode).toHaveBeenCalledWith('files')
    expect(workspace.viewDocument).toHaveBeenCalledTimes(1)
    const [uuid, title, highlight] = workspace.viewDocument.mock.calls[0]
    expect(uuid).toBe('doc-1')
    expect(title).toBe('Uniform Guidance')
    expect(highlight.page).toBe(12)
    expect(CHUNK.startsWith(highlight.terms[0])).toBe(true)
    // The server-truncated tail word never reaches the viewer.
    expect(highlight.terms[0].endsWith('otherw')).toBe(false)
  })

  it('goes straight to Preview once that document is already open', () => {
    workspace.openDocumentUuid = 'doc-1'
    render(<ChatMessage message={messageWith({ document_uuid: 'doc-1' })} />)

    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))

    expect(screen.queryByRole('menuitem')).toBeNull()
    expect(screen.getByText(/Recipients must retain/)).toBeTruthy()
  })

  it('goes straight to Preview for a source with no document behind it', () => {
    render(<ChatMessage message={messageWith({ document_uuid: null, page: null })} />)

    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))

    expect(screen.queryByRole('menuitem')).toBeNull()
    expect(screen.getByText(/Recipients must retain/)).toBeTruthy()
  })
})
