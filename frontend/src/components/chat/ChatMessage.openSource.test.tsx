import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

// Support ticket: a KB citation's preview offered "Open the source", which
// opened `document_id` — the knowledge-base SOURCE id, not a file — so the
// viewer 404'd with "Source unavailable" while the PDF sat in Files, Ready.
// The file to open is `document_uuid`, resolved server-side per reader.

const viewDocument = vi.fn()
const setWorkspaceMode = vi.fn()

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    selectedDocuments: [],
    openDocument: vi.fn(),
    viewDocument,
    setWorkspaceMode,
    openDocumentUuid: null,
  }),
}))

function messageWith(citations: Citation[]): ChatMessageType {
  return {
    role: 'assistant',
    content: 'The Project Description is limited to 15 pages.',
    citations,
  } as ChatMessageType
}

const kbSourceId = 'kb-source-1'
const fileUuid = 'smartdoc-1'

beforeEach(() => {
  viewDocument.mockClear()
  setWorkspaceMode.mockClear()
})

describe('KB citation "Open the source"', () => {
  it('opens the file at the cited page, never the KB source id', () => {
    render(<ChatMessage message={messageWith([{
      document_id: kbSourceId,
      document_uuid: fileUuid,
      document_title: 'PAPPG.pdf',
      page: 137,
      page_approximate: true,
      chunk_id: 'c1',
      content_preview: 'The Project Description must not exceed 15 pages.',
    }])} />)

    fireEvent.click(screen.getByText('PAPPG.pdf · p. ~137'))
    fireEvent.click(screen.getByText('Preview'))
    fireEvent.click(screen.getByText('Open the source'))

    expect(setWorkspaceMode).toHaveBeenCalledWith('files')
    expect(viewDocument).toHaveBeenCalledTimes(1)
    const [uuid, title, highlight] = viewDocument.mock.calls[0]
    expect(uuid).toBe(fileUuid)
    expect(title).toBe('PAPPG.pdf')
    expect(highlight).toMatchObject({ page: 137, pageApproximate: true })
  }, 20_000)

  it('offers no open button when only the KB source id is known', () => {
    render(<ChatMessage message={messageWith([{
      document_id: kbSourceId,
      document_title: 'PAPPG.pdf',
      page: 137,
      chunk_id: 'c1',
      content_preview: 'The Project Description must not exceed 15 pages.',
    }])} />)

    fireEvent.click(screen.getByText('PAPPG.pdf · p. 137'))

    expect(screen.queryByText('Open the source')).not.toBeInTheDocument()
    expect(screen.getByText(/original document is not linked/)).toBeInTheDocument()
    expect(viewDocument).not.toHaveBeenCalled()
  }, 20_000)
})
