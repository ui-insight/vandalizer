import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'
import type { ChatMessage as ChatMessageType, Citation } from '../../types/chat'

// `formatPageLocator` has its own unit tests, and they pass. What they cannot
// tell us is whether this component actually HANDS it `page_approximate`.
// The field is optional in TypeScript, so a wrong or missing prop name here
// compiles cleanly and silently renders a confident "p. 12" for a page number
// that was interpolated from OCR text — the exact invented precision #626
// exists to prevent, and the reason both PRs stayed in draft.
//
// These render the real component and assert on the DOM.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ selectedDocuments: [], openDocument: vi.fn() }),
}))

function messageWith(citations: Citation[]): ChatMessageType {
  return {
    role: 'assistant',
    content: 'The indirect cost rate is 58%.',
    citations,
  } as ChatMessageType
}

const measured: Citation = {
  document_title: 'Budget Justification',
  page: 12,
  chunk_id: 'c1',
}

const interpolated: Citation = {
  document_title: 'Scanned Proposal',
  page: 12,
  page_approximate: true,
  chunk_id: 'c2',
}

describe('ChatMessage source citations', () => {
  it('hedges a page that was interpolated from OCR text', () => {
    render(<ChatMessage message={messageWith([interpolated])} />)

    expect(screen.getByText(/Scanned Proposal · p\. ~12/)).toBeInTheDocument()
  })

  it('does not hedge a page that was measured', () => {
    render(<ChatMessage message={messageWith([measured])} />)

    expect(screen.getByText(/Budget Justification · p\. 12/)).toBeInTheDocument()
    expect(screen.queryByText(/~/)).not.toBeInTheDocument()
  })

  it('keeps the two kinds distinct in one message', () => {
    // The case that matters most: a user asking across a digital and a scanned
    // document must be able to tell which page number to trust.
    render(<ChatMessage message={messageWith([measured, interpolated])} />)

    expect(screen.getByText(/Budget Justification · p\. 12$/)).toBeInTheDocument()
    expect(screen.getByText(/Scanned Proposal · p\. ~12/)).toBeInTheDocument()
  })

  it('falls back to the sheet name for spreadsheet sources', () => {
    render(<ChatMessage message={messageWith([
      { document_title: 'Budget Workbook', sheet: 'NSF Summary', chunk_id: 'c3' },
    ])} />)

    expect(screen.getByText(/Budget Workbook · NSF Summary/)).toBeInTheDocument()
  })

  it('shows the title alone when there is no page or sheet', () => {
    render(<ChatMessage message={messageWith([
      { document_title: 'Policy Memo', chunk_id: 'c4' },
    ])} />)

    expect(screen.getByText('Policy Memo')).toBeInTheDocument()
  })
})
