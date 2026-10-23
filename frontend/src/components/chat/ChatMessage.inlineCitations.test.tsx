import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

// A knowledge-base answer cites a passage as "[Source: <label>]". It used to
// stay plain text, with the passages only in the row under the answer; now a
// citation that names a passage this turn retrieved is a chip beside the
// claim that opens that passage, as in a workflow run.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedDocuments: [], openDocument: vi.fn() }),
}))

const LABEL = 'Subpart D—Post Federal Award Requirements · § 200.308 · part 4'

const section: Citation = {
  ref: 1,
  document_title: 'Subpart D—Post Federal Award Requirements',
  label: LABEL,
  content: '(5) The transfer of funds budgeted for participant support costs to other budget categories.',
  content_preview: '(5) The transfer of funds budgeted for participant support costs',
  chunk_id: 'ug-d_chunk_41',
  used: true,
}

function answer(content: string, citations: Citation[], segmented = false): ChatMessageType {
  return {
    role: 'assistant',
    content,
    citations,
    ...(segmented ? { segments: [{ kind: 'text', content }] } : {}),
  } as ChatMessageType
}

describe('inline citation chips in chat answers', () => {
  it.each([false, true])('turns a cited passage into a chip that opens it (segments: %s)', (segmented) => {
    const { container } = render(<ChatMessage message={answer(
      `Moving participant support funds needs prior approval [Source: ${LABEL}].`, [section], segmented,
    )} />)
    const chip = container.querySelector('.chat-markdown .kb-cite') as HTMLElement
    expect(chip).not.toBeNull()
    expect(chip).toHaveAttribute('aria-label', `Citation: ${LABEL}`)
    expect(container.querySelector('.chat-markdown')).not.toHaveTextContent('[Source:')

    fireEvent.click(chip)
    expect(screen.getByRole('dialog')).toHaveTextContent('participant support costs to other budget categories')
  })

  it('chips each passage of a citation that names several', () => {
    const other: Citation = { ...section, ref: 2, label: 'Subpart E—Cost Principles · § 200.423', document_title: 'Subpart E—Cost Principles', content: 'Costs of alcoholic beverages are unallowable.', chunk_id: 'ug-e_chunk_80' }
    const { container } = render(<ChatMessage message={answer(
      `Both apply [Source: ${LABEL}; Subpart E—Cost Principles · § 200.423].`, [section, other],
    )} />)
    expect(container.querySelectorAll('.chat-markdown .kb-cite')).toHaveLength(2)
  })

  it('leaves a citation that names no retrieved passage as written', () => {
    const { container } = render(<ChatMessage message={answer(
      'Extensions need approval [Source: Subpart D—Post Federal Award Requirements · § 200.309].', [section],
    )} />)
    expect(container.querySelector('.chat-markdown .kb-cite')).toBeNull()
    expect(container.querySelector('.chat-markdown')).toHaveTextContent('[Source: Subpart D—Post Federal Award Requirements · § 200.309]')
  })

  it('chips an answer saved before passages carried their label, by title and page', () => {
    const old: Citation = { ref: 1, document_title: 'PAPPG.pdf', page: 54, chunk_id: 'p54', content_preview: 'No-cost extensions of up to 12 months…' }
    const { container } = render(<ChatMessage message={answer('Up to 12 months [Source: PAPPG.pdf, p. 54].', [old])} />)
    expect(container.querySelector('.chat-markdown .kb-cite')).not.toBeNull()
  })

  it('keeps an answer with no retrieved passages exactly as rendered before', () => {
    const { container } = render(<ChatMessage message={answer('No sources here [Source: Notes.pdf].', [])} />)
    expect(container.querySelector('.kb-cite')).toBeNull()
    expect(container.querySelector('.chat-markdown')).toHaveTextContent('[Source: Notes.pdf]')
  })
})
