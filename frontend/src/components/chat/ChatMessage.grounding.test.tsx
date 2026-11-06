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

// A web answer's exact dates taken from search snippets read like facts beside
// official links (NSF PAPPG ticket: Supplement 1 "effective Oct. 8, 2025").
describe('ChatMessage unconfirmed web details', () => {
  it('names the details no page read for the answer states', () => {
    render(<ChatMessage message={answer({
      content: 'Supplement 1 (effective Oct. 8, 2025).',
      unconfirmed_web_facts: ['Oct. 8, 2025'],
    })} />)

    const note = screen.getByRole('note', { name: 'Details not confirmed on a page' })
    expect(note).toHaveTextContent('Not confirmed on a page: Oct. 8, 2025')
    expect(note).toHaveTextContent(/web search results/)
  })

  it('shows nothing for an answer without unconfirmed web details', () => {
    render(<ChatMessage message={answer({ unconfirmed_web_facts: [] })} />)

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

  it('says when the page was matched to the file by its content (#1058)', () => {
    render(<ChatMessage message={answer({ content: 'The cap is $180,000 [p. 3].', citations: [{ ...cite('found'), document_uuid: null, attribution: 'content' as const }] })} />)
    fireEvent.click(screen.getByRole('button', { name: 'notice-v1.pdf · p. 3' }))
    expect(screen.getByText(/without naming a file/)).toBeInTheDocument()
  })

  it('leaves knowledge-base chips, which carry no grounding field, unmarked', () => {
    render(<ChatMessage message={answer({ citations: [cite(undefined)] })} />)
    expect(screen.getByRole('button', { name: 'notice-v1.pdf · p. 3' })).toBeInTheDocument()
    expect(screen.queryByText(/passage not found|not checked/)).not.toBeInTheDocument()
  })
})

// An answer that reads a gap in the sources as a rule ("may be any length")
// says so under the answer (#1012). Both quoted sentences are from the
// 2026-10-08 measured run on gpt-oss-120b.
describe('ChatMessage conclusions drawn from silence', () => {
  it('quotes each flagged sentence and tells the reader to confirm with the sponsor', () => {
    render(<ChatMessage message={answer({
      content: 'The notice sets no page limit, so it may be any length.',
      silence_inferences: [
        'The sponsor notice does not set a page-limit for the budget justification, so it may be any length.',
        'The notice does not require the PI to be a U.S. citizen; citizenship eligibility is not specified.',
      ],
    })} />)
    const note = screen.getByRole('note', { name: "Conclusion the sources don't support" })
    expect(note).toHaveTextContent("The sources don't say this either way")
    expect(note).toHaveTextContent('so it may be any length.')
    expect(note).toHaveTextContent('does not require the PI to be a U.S. citizen')
    expect(note).toHaveTextContent(/Confirm with the sponsor or the governing guide/)
  })

  it('shows nothing when no sentence was flagged', () => {
    render(<ChatMessage message={answer({ content: 'The notice does not specify a page limit. Ask the sponsor.' })} />)
    expect(screen.queryByRole('note', { name: "Conclusion the sources don't support" })).not.toBeInTheDocument()
  })
})

// "Subaward Policies" ticket: the answer cited 2 CFR 200.332, whose scraped
// copy held only the page title, for a detailed rule it never contained.
describe('ChatMessage unsupported citations', () => {
  it('names the source that does not contain what it is cited for', () => {
    render(<ChatMessage message={answer({
      content: 'A pass-through entity must evaluate risk and review reports.',
      unsupported_citations: ['2 CFR 200.332 — Requirements for pass-through entities.'],
    })} />)

    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('2 CFR 200.332 — Requirements for pass-through entities.')
    expect(note).toHaveTextContent(/doesn't\s+contain what this answer cites it for/)
    expect(note).toHaveTextContent(/general\s+knowledge/)
  })

  it('shows both notes when figures and a citation are unsupported', () => {
    render(<ChatMessage message={answer({
      unsupported_figures: ['$750,000'],
      unsupported_citations: ['Subpart F'],
    })} />)

    expect(screen.getAllByRole('note')).toHaveLength(2)
  })
})

describe('ChatMessage calculated figures', () => {
  it('lists each calculated figure with its formula, not as general knowledge', () => {
    render(<ChatMessage message={answer({
      content: 'Indirect is $51,000 ÷ $253,000 = 20.2% of direct costs.',
      calculated_figures: [{ figure: '20.2%', formula: '$51,000 ÷ $253,000 = 20.2%' }],
    })} />)

    expect(screen.getByText('Calculated from figures in the sources (1)')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Calculations', hidden: true })).toHaveTextContent('$51,000 ÷ $253,000 = 20.2%')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})
