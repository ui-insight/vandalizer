import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
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

// Answers now carry the source line a workflow run cites (`label`) and the
// whole passage (`content`). Every passage of an eCFR subpart or a policy web
// page used to read as the bare source name; where the passage sits is what
// tells them apart. Answers saved before keep the lines above.
describe('ChatMessage source lines', () => {
  const SECTION_LINE = 'OMB Uniform Guidance — Subpart D · § 200.308 · part 2'
  const section: Citation = {
    document_title: 'OMB Uniform Guidance — Subpart D',
    label: SECTION_LINE,
    chunk_id: 'c5',
  }

  it('names a passage of a source without pages by where it sits', () => {
    render(<ChatMessage message={messageWith([section])} />)

    expect(screen.getByRole('button', { name: SECTION_LINE })).toBeInTheDocument()
  })

  it('tells two passages of one source apart', () => {
    render(<ChatMessage message={messageWith([
      { document_title: 'Subpart E', label: 'Subpart E · § 200.423', chunk_id: 'c6' },
      { document_title: 'Subpart E', label: 'Subpart E · Appendix III · part 4', chunk_id: 'c7' },
    ])} />)

    expect(screen.getByRole('button', { name: 'Subpart E · § 200.423' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subpart E · Appendix III · part 4' })).toBeInTheDocument()
  })

  it('never offers "part 2" as a page to open at', () => {
    render(<ChatMessage message={messageWith([{ ...section, document_uuid: 'doc-ug' }])} />)

    fireEvent.click(screen.getByRole('button', { name: SECTION_LINE }))

    expect(screen.getByRole('menuitem', { name: 'Open document' })).toBeInTheDocument()
    expect(screen.queryByText(/p\. ~?2/)).not.toBeInTheDocument()
  })

  it('keeps the knowledge base after the line on a multi-KB turn', () => {
    render(<ChatMessage message={messageWith([
      { document_title: 'PAPPG.pdf', page: 54, label: 'PAPPG.pdf · p. 54', kb_title: 'NSF Policies', chunk_id: 'c8' },
    ])} />)

    expect(screen.getByRole('button', { name: 'PAPPG.pdf · p. 54 · NSF Policies' })).toBeInTheDocument()
  })

  it('previews the whole passage under its line, scrolling inside a bounded box', () => {
    const passage = `${'Costs must be necessary and reasonable for the award. '.repeat(8)}Advertising costs are allowable only for recruitment.`
    render(<ChatMessage message={messageWith([{ ...section, content: passage, content_preview: passage.slice(0, 240) }])} />)

    fireEvent.click(screen.getByRole('button', { name: SECTION_LINE }))

    const box = screen.getByRole('region', { name: 'Source passage' })
    // Past the 240-character preview: the claim may rest on the end of it.
    expect(box).toHaveTextContent(/Advertising costs are allowable only for recruitment\.$/)
    expect(box).toHaveStyle({ maxHeight: '260px', overflowY: 'auto' })
    // The chip and the preview's heading.
    expect(screen.getAllByText(SECTION_LINE)).toHaveLength(2)
  })

  it('previews the saved opening of an answer from before the whole passage was sent', () => {
    render(<ChatMessage message={messageWith([{ ...measured, content_preview: 'Indirect costs are charged at 58% of MTDC.' }])} />)

    fireEvent.click(screen.getByRole('button', { name: 'Budget Justification · p. 12' }))

    expect(screen.getByRole('region', { name: 'Source passage' })).toHaveTextContent('Indirect costs are charged at 58% of MTDC.')
    expect(screen.getAllByText('Budget Justification · p. 12')).toHaveLength(2)
  })
})
