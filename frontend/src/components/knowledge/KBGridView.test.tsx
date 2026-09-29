import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { KBGridView } from './KBGridView'
import type { KnowledgeBase } from '../../types/knowledge'

let failure: Error | null = null
const refresh = vi.fn()
const kbs: { current: KnowledgeBase[] } = { current: [] }

vi.mock('../../hooks/useKnowledgeBases', () => ({
  useScopedKnowledgeBases: () => ({
    knowledgeBases: kbs.current,
    total: kbs.current.length,
    loading: false,
    refresh,
    error: failure,
  }),
}))

function makeKB(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    uuid: 'kb-1',
    title: 'Export Control Regulations',
    description: '',
    status: 'ready',
    shared_with_team: false,
    team_owned: false,
    verified: false,
    organization_ids: [],
    tags: [],
    team_id: null,
    total_sources: 3,
    sources_ready: 3,
    sources_failed: 0,
    total_chunks: 120,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  }
}

const baseProps = {
  scope: 'mine' as const,
  search: '',
  allOrgs: [],
  onSelect: vi.fn(),
  onChat: vi.fn(),
}

// Support ticket regression guard: the card-level Clone action was lost once
// before in a KBCard→KBGridView refactor merge, leaving the backend clone
// endpoint with no UI. These tests pin the button to the card.
describe('KBGridView clone action', () => {
  beforeEach(() => {
    failure = null
    vi.clearAllMocks()
    kbs.current = [makeKB()]
  })

  it('shows Clone on a KB card and reports the KB uuid', () => {
    const onClone = vi.fn()
    render(<KBGridView {...baseProps} onClone={onClone} />)

    fireEvent.click(screen.getByText('Clone'))
    expect(onClone).toHaveBeenCalledWith('kb-1')
  })

  it('clones the source KB, not the bookmark, for a reference card', () => {
    kbs.current = [makeKB({
      uuid: 'ref-view-uuid',
      is_reference: true,
      source_kb_uuid: 'canonical-kb',
      reference_uuid: 'bookmark-1',
    })]
    const onClone = vi.fn()
    render(<KBGridView {...baseProps} onClone={onClone} />)

    fireEvent.click(screen.getByText('Clone'))
    expect(onClone).toHaveBeenCalledWith('canonical-kb')
  })

  it('offers no Clone on a broken bookmark — there is nothing to copy', () => {
    kbs.current = [makeKB({
      uuid: 'ref-view-uuid',
      status: 'unavailable',
      is_reference: true,
      reference_uuid: 'bookmark-1',
    })]
    render(<KBGridView {...baseProps} onClone={vi.fn()} onRemoveRef={vi.fn()} />)

    expect(screen.queryByText('Clone')).not.toBeInTheDocument()
  })

  it('renders no Clone button when no handler is wired', () => {
    render(<KBGridView {...baseProps} />)

    expect(screen.queryByText('Clone')).not.toBeInTheDocument()
  })

  // Support ticket: cloning a KB with no sources produced a second empty KB.
  it('disables Clone on a KB with no sources, and says why', () => {
    kbs.current = [makeKB({
      status: 'empty',
      total_sources: 0,
      sources_ready: 0,
      total_chunks: 0,
    })]
    const onClone = vi.fn()
    render(<KBGridView {...baseProps} onClone={onClone} />)

    const button = screen.getByText('Clone').closest('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'This knowledge base has no sources to copy yet')

    fireEvent.click(screen.getByText('Clone'))
    expect(onClone).not.toHaveBeenCalled()
  })
})


describe('knowledge scope and availability', () => {
  beforeEach(() => { failure = null; vi.clearAllMocks(); kbs.current = [makeKB()] })
  it('keeps read-only KBs usable without exposing mutation controls', () => {
    kbs.current = [makeKB({ can_manage: false, shared_with_team: true })]
    render(<KBGridView {...baseProps} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.getByText('Read only')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
    expect(baseProps.onChat).toHaveBeenCalledWith('kb-1', 'Export Control Regulations')
  })
  it('opens and chats with the canonical target of a bookmark', () => {
    kbs.current = [makeKB({ uuid: 'reference-view', is_reference: true, source_kb_uuid: 'canonical-kb', reference_uuid: 'bookmark' })]
    render(<KBGridView {...baseProps} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export Control Regulations' }))
    fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
    expect(baseProps.onSelect).toHaveBeenCalledWith('canonical-kb')
    expect(baseProps.onChat).toHaveBeenCalledWith('canonical-kb', 'Export Control Regulations')
  })
  it('offers retry instead of an empty explainer after a list failure', () => {
    kbs.current = []; failure = new Error('offline')
    render(<KBGridView {...baseProps} emptyComponent={<p>Start here</p>} />)
    expect(screen.queryByText('Start here')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading knowledge bases' }))
    expect(refresh).toHaveBeenCalledOnce()
  })
  it('retains the last list when refreshing fails', () => {
    failure = new Error('offline')
    render(<KBGridView {...baseProps} />)
    expect(screen.getByRole('button', { name: 'Export Control Regulations' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Showing the last loaded list')
  })
})
