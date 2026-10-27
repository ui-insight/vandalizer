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

// ChatMessage calls useToast on this branch; matches the idiom used by the
// other component suites.
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('../../api/feedback', () => ({
  submitChatFeedback: vi.fn(),
}))

const CHUNK =
  'Recipients must retain financial records for three years after submission '
  + 'of the final expenditure report, unless the awarding agency directs otherw'

it.each(['user', 'assistant'] as const)('offers Copy and Export for a %s bubble without rating controls', role => {
  render(<ChatMessage message={{ role, content: 'Hello' }} />)
  expect(screen.getByRole('button', { name: 'Copy message' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Export message' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Good response' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Poor response' })).not.toBeInTheDocument()
})

it('offers export for a completed tool-only response but hides actions while streaming', () => {
  const message: ChatMessageType = { role: 'assistant', content: '', tool_results: [{ tool_name: 'some_tool', tool_call_id: 't1', content: { status: 'done' }, quality: null }] }
  const { rerender } = render(<ChatMessage message={message} />)
  expect(screen.getByRole('button', { name: 'Export message' })).toBeInTheDocument()
  rerender(<ChatMessage message={message} isStreaming />)
  expect(screen.queryByRole('button', { name: 'Export message' })).not.toBeInTheDocument()
})

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
    expect(workspace.viewDocument.mock.calls[0][3]).toEqual({ preserveChatScope: true })
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


describe('citation menu keyboard navigation', () => {
  it('focuses the menu, supports arrow keys, and returns Escape focus to the citation', () => {
    workspace.openDocumentUuid = null
    render(<ChatMessage message={messageWith({ document_uuid: 'document-1', page_approximate: true })} />)
    const citation = screen.getByRole('button', { name: /Uniform Guidance · p. ~12/ })
    fireEvent.click(citation)
    expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Preview' }))
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Open at p. ~12' }))
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(document.activeElement).toBe(citation)
  })
})

describe('document links in an answer', () => {
  beforeEach(() => {
    workspace.setWorkspaceMode.mockClear()
    workspace.viewDocument.mockClear()
  })

  it('opens the linked document and makes it the chat document', () => {
    // Support ticket: chat offered two NOA files by name, and neither could be
    // clicked. Picking one should open it and attach it, so "run it" uses it.
    render(<ChatMessage message={{
      role: 'assistant',
      content: 'Which one?\n\n- [NOA_G26AC00033-00.pdf](doc:doc-noa-1)\n- [Award.PDF](doc:doc-noa-2)',
    }} />)
    fireEvent.click(screen.getByRole('button', { name: 'NOA_G26AC00033-00.pdf' }))
    expect(workspace.setWorkspaceMode).toHaveBeenCalledWith('files')
    // No preserveChatScope: opening it replaces the chat's documents.
    expect(workspace.viewDocument.mock.calls).toEqual([['doc-noa-1', 'NOA_G26AC00033-00.pdf']])
  })
})
