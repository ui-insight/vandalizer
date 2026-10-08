import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine, listErrorEntry } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// search_knowledge_base returns a list, so it sends a failure or a "nothing
// matched" note as a one-item list. Both used to read "Found 1 relevant
// passage", and the failure showed as a success (#997).
const call = { tool_name: 'search_knowledge_base', tool_call_id: 'kb-1', args: { query: 'equipment threshold' } }
const searched = (content: unknown) => ({ tool_name: 'search_knowledge_base', tool_call_id: 'kb-1', content, quality: null })

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

  it('unwraps only a lone error entry', () => {
    expect(listErrorEntry([{ error: 'x' }])).toEqual({ error: 'x' })
    expect(listErrorEntry([{ error: 'x' }, { content: 'y' }])).toBeNull()
    expect(listErrorEntry([{ content: 'y' }])).toBeNull()
    expect(listErrorEntry({ error: 'x' })).toBeNull()
  })
})
