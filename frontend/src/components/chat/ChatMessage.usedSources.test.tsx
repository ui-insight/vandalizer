import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

// Support ticket: a "QA Smoke doesn't contain the DOE travel rules" answer
// showed 7–10 PAPPG.pdf chips under "Sources:". Only snippets the answer cited
// are sources; the rest were searched but not used.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedDocuments: [], openDocument: vi.fn() }),
}))

const chip = (ref: number, page: number, used?: boolean): Citation => ({
  document_title: 'PAPPG.pdf', page, chunk_id: `c${ref}`, ref, ...(used === undefined ? {} : { used }),
})

function answer(content: string, citations: Citation[]): ChatMessageType {
  return { role: 'assistant', content, citations } as ChatMessageType
}

describe('ChatMessage used vs searched sources', () => {
  it('lists no sources under a not-found answer, only the searched count', () => {
    render(<ChatMessage message={answer(
      'The QA Smoke knowledge base does not contain DOE travel reimbursement rules.',
      [chip(1, 54, false), chip(2, 139, false), chip(3, 212, false)],
    )} />)

    expect(screen.queryByText('Sources:')).not.toBeInTheDocument()
    expect(screen.queryByText(/PAPPG\.pdf · p\. 54/)).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /Searched but not used \(3\)/ })
    fireEvent.click(toggle)
    expect(screen.getByText(/PAPPG\.pdf · p\. 54/)).toBeInTheDocument()
  })

  it('lists only the cited snippet as a source', () => {
    render(<ChatMessage message={answer(
      'Up to 12 months [Source: PAPPG.pdf, p. 139].',
      [chip(1, 54, false), chip(2, 139, true), chip(3, 212, false)],
    )} />)

    expect(screen.getByText('Sources:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /PAPPG\.pdf · p\. 139/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /PAPPG\.pdf · p\. 212/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Searched but not used \(2\)/ })).toBeInTheDocument()
  })

  it('shows every chip as a source on answers saved before the distinction', () => {
    render(<ChatMessage message={answer('Old answer.', [chip(1, 54), chip(2, 139)])} />)

    expect(screen.getByText('Sources:')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /p\. 54/ })).toBeInTheDocument()
    expect(screen.queryByText(/Searched but not used/)).not.toBeInTheDocument()
  })
})
