import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation, ClaimChecks } from '../../types/chat'

// Each cited claim of a KB answer is checked against the passage it cites
// (backend chat_claim_check). A chip whose claim the passage does not state
// is marked, and its popover says so; a verified claim's popover highlights
// the excerpt it rests on. A passage holding only items of a list shows the
// list's lead-in above it.

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

const LABEL_5 = 'Subpart D—Post Federal Award Requirements · § 200.308 · part 5'
const LABEL_4 = 'Subpart D—Post Federal Award Requirements · § 200.308 · part 4'
const LEAD = '(f) Revisions Requiring Prior Approval. A recipient must request prior written approval for the following:'

const part5: Citation = {
  ref: 1,
  document_title: 'Subpart D—Post Federal Award Requirements',
  label: LABEL_5,
  content: 'All requests for no-cost extensions should be submitted at least 10 calendar days before the conclusion. The Federal agency may approve multiple no-cost extensions.',
  chunk_id: 'ug_chunk_37',
  lead_in: LEAD,
  used: true,
}
const part4: Citation = { ...part5, ref: 2, label: LABEL_4, chunk_id: 'ug_chunk_36', content: '(5) The transfer of funds budgeted for participant support costs.' }

const ANSWER = [
  `- Requests must be submitted at least 10 calendar days before the end [Source: ${LABEL_5}].`,
  `- The agency may approve multiple no-cost extensions [Source: ${LABEL_5}].`,
].join('\n')

const CHECKS: ClaimChecks = {
  version: 1,
  claims: [
    { claim: 'Requests must be submitted at least 10 calendar days before the end', citations: [`Source: ${LABEL_5}`], cites: [0], status: 'unverified', reason: 'obligation_differs' },
    { claim: 'The agency may approve multiple no-cost extensions', citations: [`Source: ${LABEL_5}`], cites: [0], status: 'verified', reason: 'ok', quote: 'The Federal agency may approve multiple no-cost extensions.' },
  ],
}

function answer(content: string, citations: Citation[], claim_checks?: ClaimChecks, segmented = false): ChatMessageType {
  return {
    role: 'assistant', content, citations, claim_checks,
    ...(segmented ? { segments: [{ kind: 'text', content }] } : {}),
  } as ChatMessageType
}

describe('claim checks on chat citation chips', () => {
  it.each([false, true])('marks the chip of a claim its passage does not state (segments: %s)', (segmented) => {
    const { container } = render(<ChatMessage message={answer(ANSWER, [part5], CHECKS, segmented)} />)
    const chips = container.querySelectorAll('.chat-markdown .kb-cite')
    expect(chips).toHaveLength(2)
    expect(chips[0]).toHaveClass('kb-cite-unverified')
    expect(chips[0]).toHaveAttribute('aria-label', `Citation, not confirmed by the passage: ${LABEL_5}`)
    expect(chips[1]).not.toHaveClass('kb-cite-unverified')

    fireEvent.click(chips[0])
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Not confirmed.')
    expect(dialog).toHaveTextContent('"must" where the passage says "should"')
    expect(dialog).toHaveTextContent('Requests must be submitted at least 10 calendar days before the end')
  })

  it('highlights the excerpt a verified claim rests on', () => {
    const { container } = render(<ChatMessage message={answer(ANSWER, [part5], CHECKS)} />)
    fireEvent.click(container.querySelectorAll('.chat-markdown .kb-cite')[1])
    const dialog = screen.getByRole('dialog')
    expect(dialog).not.toHaveTextContent('Not confirmed.')
    expect(dialog.querySelector('mark')).toHaveTextContent('The Federal agency may approve multiple no-cost extensions.')
  })

  it("shows the list's lead-in above a passage of its items", () => {
    const { container } = render(<ChatMessage message={answer(
      `Moving them needs prior approval [Source: ${LABEL_4}].`, [part4],
    )} />)
    fireEvent.click(container.querySelector('.chat-markdown .kb-cite') as HTMLElement)
    expect(screen.getByRole('dialog')).toHaveTextContent(LEAD)
  })

  it('leaves the chips as they were when the answer carries no checks', () => {
    const { container } = render(<ChatMessage message={answer(ANSWER, [part5])} />)
    expect(container.querySelector('.kb-cite-unverified')).toBeNull()
    expect(container.querySelectorAll('.chat-markdown .kb-cite')).toHaveLength(2)
  })

  it('does not mark a chip by a check of another claim citing the same passage', () => {
    const other: ClaimChecks = { version: 1, claims: [{ ...CHECKS.claims[0], claim: 'Something the answer never says here' }] }
    const { container } = render(<ChatMessage message={answer(ANSWER, [part5], other)} />)
    expect(container.querySelector('.kb-cite-unverified')).toBeNull()
  })
})
