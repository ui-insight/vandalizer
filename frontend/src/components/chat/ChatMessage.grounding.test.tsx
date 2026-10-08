import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType } from '../../types/chat'

// A KB answer whose figure no retrieved snippet states must say so under the
// answer — the 2 CFR 200 ticket's $750,000 single-audit threshold was
// recalled from the model's memory and read exactly like a cited fact.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
// ChatMessage calls useToast on this branch.
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedDocuments: [], openDocument: vi.fn() }),
}))

function answer(extra: Partial<ChatMessageType> = {}): ChatMessageType {
  return { role: 'assistant', content: 'The single audit threshold is $750,000.', ...extra }
}

describe('ChatMessage unsupported figures', () => {
  it('names the figures no retrieved source states', () => {
    render(<ChatMessage message={answer({ unsupported_figures: ['$750,000'] })} />)

    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('Not in the retrieved sources: $750,000')
    expect(note).toHaveTextContent(/general knowledge/)
  })

  it('shows nothing when every figure is grounded', () => {
    render(<ChatMessage message={answer()} />)

    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

// A chip made from a page number the model wrote about an attached document is
// only shown as an ordinary source when the cited sentence was found on that
// page (#998). Otherwise it still opens the page, but says what it is.
describe('ChatMessage page citations on attached documents', () => {
  const cite = (grounding?: 'found' | 'not_found' | 'unchecked') => ({
    document_uuid: 'notice-v1', document_title: 'notice-v1.pdf', page: 3,
    content_preview: 'The maximum direct-cost request is $180,000.', grounding,
  })

  it('shows a citation whose passage was found as an ordinary source', () => {
    render(<ChatMessage message={answer({ content: 'The cap is $180,000 (p. 3).', citations: [cite('found')] })} />)
    expect(screen.getByRole('button', { name: 'notice-v1.pdf · p. 3' })).toBeInTheDocument()
  })

  it.each([
    ['not_found', 'notice-v1.pdf · p. 3 · passage not found', /what it said was not found there/],
    ['unchecked', 'notice-v1.pdf · p. 3 · not checked', /without a figure, date, quote or wording/],
  ] as const)('marks a %s citation on the chip and explains it in the preview', (grounding, name, explanation) => {
    render(<ChatMessage message={answer({ content: 'The cap is $200,000 (p. 3).', citations: [{ ...cite(grounding), document_uuid: null }] })} />)
    fireEvent.click(screen.getByRole('button', { name }))
    expect(screen.getByText(explanation)).toBeInTheDocument()
    expect(screen.getByText(/top of the page, not a supporting passage/)).toBeInTheDocument()
  })

  it('leaves knowledge-base chips, which carry no grounding field, unmarked', () => {
    render(<ChatMessage message={answer({ citations: [cite(undefined)] })} />)
    expect(screen.getByRole('button', { name: 'notice-v1.pdf · p. 3' })).toBeInTheDocument()
    expect(screen.queryByText(/passage not found|not checked/)).not.toBeInTheDocument()
  })
})
