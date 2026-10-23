import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine, listErrorEntry, toolResultToText } from './ToolCallDisplay'
import type { Citation } from '../../types/chat'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// search_knowledge_base returns a list, so it sends a failure or a "nothing
// matched" note as a one-item list. Both used to read "Found 1 relevant
// passage", and the failure showed as a success (#997).
const call = { tool_name: 'search_knowledge_base', tool_call_id: 'kb-1', args: { query: 'equipment threshold' } }
const searched = (content: unknown) => ({ tool_name: 'search_knowledge_base', tool_call_id: 'kb-1', content, quality: null })

describe('a workflow output shown in chat', () => {
  const LABEL = 'OMB Uniform Guidance — Subpart D · § 200.308 · part 2'
  const wfCall = { tool_name: 'get_workflow_status', tool_call_id: 'wf-1', args: { session_id: 's-1' } }
  const finished = (sources?: Citation[]) => ({
    tool_name: 'get_workflow_status', tool_call_id: 'wf-1', quality: null,
    content: { status: 'completed', output: `Rebudgeting participant support costs needs prior approval [${LABEL}].` },
    ...(sources ? { sources } : {}),
  })
  const passage: Citation = {
    document_title: 'Subpart D', kb_title: 'OMB Uniform Guidance', label: LABEL, chunk_id: 'ug-d_chunk_41',
    content: '(5) The transfer of funds budgeted for participant support costs to other budget categories.',
  }

  it('shows the passages the output cites as chips that open them', () => {
    const { container } = render(<ToolStatusLine call={wfCall} result={finished([passage])} />)
    const chip = container.querySelector('.chat-markdown .kb-cite') as HTMLElement
    expect(chip).toHaveAttribute('aria-label', `Citation: ${LABEL}`)
    fireEvent.click(chip)
    expect(screen.getByRole('dialog')).toHaveTextContent('participant support costs to other budget categories')
  })

  it('leaves the citation as written when the run sent no passages', () => {
    const { container } = render(<ToolStatusLine call={wfCall} result={finished()} />)
    expect(container.querySelector('.kb-cite')).toBeNull()
    expect(container.querySelector('.chat-markdown')).toHaveTextContent(`[${LABEL}]`)
  })
})

describe('knowledge base search results', () => {
  it.each([
    ['a failed search', 'Knowledge base search FAILED for "2 CFR 200" — the retrieval backend returned an error.'],
    ['a knowledge base still indexing', 'Knowledge base "2 CFR 200" is currently building. Try again in a few minutes once indexing completes.'],
    ['no access', 'You do not have access to this knowledge base.'],
  ])('shows %s as a failure with its message', (_case, message) => {
    render(<ToolStatusLine call={call} result={searched([{ error: message, hint: 'Tell the user the search itself failed.' }])} />)
    expect(screen.getByRole('status')).toHaveTextContent('Failed')
    expect(screen.queryByText(/relevant passage/)).toBeNull()
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.getByText('Tell the user the search itself failed.')).toBeInTheDocument()
  })

  it('shows a search that matched nothing as no passages, not one', () => {
    render(<ToolStatusLine call={call} result={searched([{ no_results: true, note: 'No content matched this query.' }])} />)
    expect(screen.getByText('No matching passages')).toBeInTheDocument()
    expect(screen.queryByText(/relevant passage/)).toBeNull()
    expect(screen.getByRole('status')).not.toHaveTextContent('Failed')
  })

  it('still counts real passages', () => {
    render(<ToolStatusLine call={call} result={searched([
      { content: 'Equipment means tangible personal property…', source_name: '2 CFR 200.1', page: 3 },
      { content: 'MTDC excludes equipment…', source_name: '2 CFR 200.1', page: 4 },
    ])} />)
    expect(screen.getByText('Found 2 relevant passages')).toBeInTheDocument()
  })

  it('names each passage by the line it is cited by, and copies that line', () => {
    // A source without pages: both passages used to read "Subpart E".
    const passages = [
      { content: 'Advertising costs are allowable only for recruitment…', source_name: 'Subpart E', label: 'Subpart E · § 200.421' },
      { content: 'Rate agreements negotiated with the cognizant agency…', source_name: 'Subpart E', label: 'Subpart E · Appendix III · part 4' },
    ]
    render(<ToolStatusLine call={call} result={searched(passages)} />)

    expect(screen.getByText('Subpart E · § 200.421')).toBeInTheDocument()
    expect(screen.getByText('Subpart E · Appendix III · part 4')).toBeInTheDocument()
    expect(screen.queryByText('Subpart E')).toBeNull()
    expect(toolResultToText('search_knowledge_base', passages)).toBe(
      '[Subpart E · § 200.421]\nAdvertising costs are allowable only for recruitment…\n\n'
      + '[Subpart E · Appendix III · part 4]\nRate agreements negotiated with the cognizant agency…',
    )
  })

  it('keeps the source name for results saved before the line was sent', () => {
    const passages = [{ content: 'Equipment means tangible personal property…', source_name: '2 CFR 200.1', page: 3 }]
    render(<ToolStatusLine call={call} result={searched(passages)} />)

    expect(screen.getByText('2 CFR 200.1')).toBeInTheDocument()
    expect(toolResultToText('search_knowledge_base', passages)).toBe('[2 CFR 200.1]\nEquipment means tangible personal property…')
  })

  it('unwraps only a lone error entry', () => {
    expect(listErrorEntry([{ error: 'x' }])).toEqual({ error: 'x' })
    expect(listErrorEntry([{ error: 'x' }, { content: 'y' }])).toBeNull()
    expect(listErrorEntry([{ content: 'y' }])).toBeNull()
    expect(listErrorEntry({ error: 'x' })).toBeNull()
  })
})
