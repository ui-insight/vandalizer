import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType } from '../../types/chat'

// A KB answer whose figure no retrieved snippet states must say so under the
// answer — the 2 CFR 200 ticket's $750,000 single-audit threshold was
// recalled from the model's memory and read exactly like a cited fact.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
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
