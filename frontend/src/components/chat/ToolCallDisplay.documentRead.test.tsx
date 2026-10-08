import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// A partial read of a long document must say which pages it covered (#1007).
const call = { tool_name: 'get_document_text', tool_call_id: 'read-1', args: { document_uuid: 'doc-1' } }
const read = (content: unknown) => ({ tool_name: 'get_document_text', tool_call_id: 'read-1', content, quality: null })

describe('document read summary', () => {
  it('names the pages a partial read covered', () => {
    render(<ToolStatusLine call={call} result={read({ title: 'Solicitation.pdf', pages_returned: '1–29', page_count: 104, complete: false, total_chars: 104000 })} />)
    expect(screen.getByText('"Solicitation.pdf" - read pp. 1–29 of 104')).toBeInTheDocument()
  })

  it('says when every page was read', () => {
    render(<ToolStatusLine call={call} result={read({ title: 'Notice.pdf', pages_returned: '1–4', page_count: 4, complete: true, total_chars: 4000 })} />)
    expect(screen.getByText('"Notice.pdf" - all 4 pages')).toBeInTheDocument()
  })

  it('marks a partial read of a document without pages', () => {
    render(<ToolStatusLine call={call} result={read({ title: 'notes.docx', total_chars: 70000, complete: false, start_char: 0, end_char: 30000 })} />)
    expect(screen.getByText('"notes.docx" - 70K chars, partly read')).toBeInTheDocument()
  })
})
