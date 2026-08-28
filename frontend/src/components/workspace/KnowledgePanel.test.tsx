import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { KnowledgePanel } from './KnowledgePanel'
import type { KnowledgeBaseDetail } from '../../types/knowledge'

const detail: { current: Partial<KnowledgeBaseDetail> } = { current: {} }
const getKnowledgeBase = vi.fn(async (_uuid: string) => detail.current as KnowledgeBaseDetail)

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    activateKB: vi.fn(),
    activeProjectUuid: null,
    activeProjectTitle: null,
    activeProjectRole: null,
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'viewer', email: 'viewer@example.com', name: 'Viewer', is_admin: false, is_examiner: false, current_team: null },
    loading: false,
  }),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('../shared/useConfirm', () => ({
  useConfirm: () => vi.fn().mockResolvedValue(true),
}))

vi.mock('../../hooks/useKnowledgeBases', () => ({
  useKnowledgeBases: () => ({
    knowledgeBases: [],
    loading: false,
    refresh: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
    transferToTeam: vi.fn(),
  }),
  useScopedKnowledgeBases: () => ({
    knowledgeBases: [],
    total: 0,
    loading: false,
    refresh: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
    transferToTeam: vi.fn(),
    adopt: vi.fn(),
    removeRef: vi.fn(),
  }),
}))

vi.mock('../../hooks/useProjectPins', () => ({
  useProjectPins: () => ({
    pins: [],
    loading: false,
    refresh: vi.fn(),
    idsByType: () => [],
    isPinned: () => false,
    pin: vi.fn(),
    unpin: vi.fn(),
  }),
}))

const refreshKBSource = vi.fn().mockResolvedValue({ ok: true, status: 'queued', source_uuid: 'src-1' })

vi.mock('../../api/knowledge', () => ({
  getKnowledgeBase: (uuid: string) => getKnowledgeBase(uuid),
  getKBQuality: vi.fn().mockResolvedValue({}),
  getKBSourceHealth: vi.fn().mockResolvedValue({}),
  refreshKBSource: (uuid: string, sourceUuid: string) => refreshKBSource(uuid, sourceUuid),
}))

vi.mock('../../api/organizations', () => ({
  listOrganizationsFlat: vi.fn().mockResolvedValue({ organizations: [] }),
}))

// The list view is irrelevant here; stub it down to a button that opens the
// detail pane for a fixed KB uuid.
vi.mock('../knowledge/KBGridView', () => ({
  KBGridView: ({ onSelect }: { onSelect: (uuid: string) => void }) => (
    <button onClick={() => onSelect('kb-1')}>open-kb</button>
  ),
}))

vi.mock('../knowledge/KBValidationPanel', () => ({ KBValidationPanel: () => null }))
vi.mock('../knowledge/KBExploreTab', () => ({ KBExploreTab: () => null }))
vi.mock('../knowledge/KBSourceInspectorModal', () => ({ KBSourceInspectorModal: () => null }))
vi.mock('../knowledge/CreateKBModal', () => ({ CreateKBModal: () => null }))
vi.mock('../knowledge/DocumentPickerModal', () => ({ DocumentPickerModal: () => null }))
vi.mock('../knowledge/AddUrlsModal', () => ({ AddUrlsModal: () => null }))
vi.mock('../knowledge/KBTrustBanner', () => ({ KBTrustBanner: () => null }))
vi.mock('./KnowledgeExplainer', () => ({ KnowledgeExplainer: () => null }))
vi.mock('./AutomationsPanel', () => ({ ExplainerPill: () => null }))
vi.mock('../library/ShareWithTeamDialog', () => ({ ShareWithTeamDialog: () => null }))
vi.mock('../shared/SharedKBDeleteDialog', () => ({ SharedKBDeleteDialog: () => null }))

function makeDetail(overrides: Partial<KnowledgeBaseDetail> = {}): Partial<KnowledgeBaseDetail> {
  return {
    uuid: 'kb-1',
    title: 'Export Control Regulations',
    description: 'Catalog KB',
    status: 'ready',
    shared_with_team: false,
    team_owned: false,
    verified: true,
    organization_ids: [],
    tags: [],
    team_id: null,
    total_sources: 3,
    sources_ready: 3,
    sources_failed: 0,
    total_chunks: 120,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    sources: [],
    ...overrides,
  }
}

async function openDetail() {
  render(<KnowledgePanel />)
  fireEvent.click(screen.getByText('open-kb'))
  // The panel is a large tree; jsdom's first render of it is slow, so allow
  // well past the 5s default.
  await waitFor(
    () => expect(screen.getByText('Add Documents')).toBeInTheDocument(),
    { timeout: 20000 },
  )
}

describe('KnowledgePanel add-source permissions', () => {
  beforeEach(() => {
    getKnowledgeBase.mockClear()
  })

  it('disables Add Documents and Add URLs when the user cannot manage the KB', async () => {
    detail.current = makeDetail({ can_manage: false })
    await openDetail()

    expect(screen.getByText('Add Documents').closest('button')).toBeDisabled()
    expect(screen.getByText('Add URLs').closest('button')).toBeDisabled()
    // Disabled buttons can't be hovered by keyboard/touch users, so the reason
    // is also stated visibly.
    expect(
      screen.getByText(/You don't have permission to manage this knowledge base/),
    ).toBeInTheDocument()
  }, 30000)

  it('enables them when the user can manage the KB', async () => {
    detail.current = makeDetail({ can_manage: true })
    await openDetail()

    expect(screen.getByText('Add Documents').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Add URLs').closest('button')).not.toBeDisabled()
    expect(
      screen.queryByText(/You don't have permission to manage this knowledge base/),
    ).not.toBeInTheDocument()
  }, 30000)

  it('treats a missing can_manage (older API response) as manageable', async () => {
    detail.current = makeDetail()
    await openDetail()

    expect(screen.getByText('Add Documents').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Add URLs').closest('button')).not.toBeDisabled()
  }, 30000)

  // Every other write action in this pane hits a manage-gated endpoint too, so
  // none of them may be offered to a viewer.
  it('hides the rename, description, share and per-source edit actions', async () => {
    detail.current = makeDetail({
      can_manage: false,
      sources: [{
        uuid: 'src-1',
        source_type: 'url',
        url: 'https://example.gov/rule',
        url_title: 'A Rule',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
      }],
    })
    await openDetail()

    expect(screen.queryByLabelText('Edit title')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Edit description')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Rename source')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Refresh source')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Remove source')).not.toBeInTheDocument()
    expect(screen.getByText('Share with Team').closest('button')).toBeDisabled()
    // Read-only actions stay available.
    expect(screen.getByText('Chat with this KB').closest('button')).not.toBeDisabled()
    expect(screen.getByText('Export').closest('button')).not.toBeDisabled()
  }, 30000)

  it('offers those actions to a user who can manage the KB', async () => {
    detail.current = makeDetail({
      can_manage: true,
      sources: [{
        uuid: 'src-1',
        source_type: 'url',
        url: 'https://example.gov/rule',
        url_title: 'A Rule',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
      }],
    })
    await openDetail()

    expect(screen.getByLabelText('Edit title')).toBeInTheDocument()
    expect(screen.getByLabelText('Edit description')).toBeInTheDocument()
    expect(screen.getByLabelText('Rename source')).toBeInTheDocument()
    expect(screen.getByLabelText('Refresh source')).toBeInTheDocument()
    expect(screen.getByLabelText('Remove source')).toBeInTheDocument()
    expect(screen.getByText('Share with Team').closest('button')).not.toBeDisabled()
  }, 30000)

  // Support ticket: a URL source's snapshot was years stale and re-adding the
  // URL was a silent no-op. Refresh re-fetches the page in place.
  it('re-fetches a URL source from the Refresh button', async () => {
    detail.current = makeDetail({
      can_manage: true,
      sources: [{
        uuid: 'src-1',
        source_type: 'url',
        url: 'https://example.gov/rule',
        url_title: 'A Rule',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
        processed_at: '2026-04-27T00:00:00Z',
      }],
    })
    await openDetail()

    fireEvent.click(screen.getByLabelText('Refresh source'))
    await waitFor(() => expect(refreshKBSource).toHaveBeenCalledWith('kb-1', 'src-1'))
  }, 30000)

  it('offers no Refresh on document sources', async () => {
    detail.current = makeDetail({
      can_manage: true,
      sources: [{
        uuid: 'src-2',
        source_type: 'document',
        document_uuid: 'doc-1',
        document_title: 'Uploaded policy.pdf',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
      }],
    })
    await openDetail()

    expect(screen.queryByLabelText('Refresh source')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Remove source')).toBeInTheDocument()
  }, 30000)
})

// Support ticket: an empty KB disabled Chat and the whole validation family,
// but Export happily downloaded a file with no sources in it.
describe('KnowledgePanel export on an empty KB', () => {
  beforeEach(() => {
    getKnowledgeBase.mockClear()
  })

  it('disables Export until the KB has a source, and says why', async () => {
    detail.current = makeDetail({
      status: 'empty',
      total_sources: 0,
      sources_ready: 0,
      total_chunks: 0,
      sources: [],
    })
    await openDetail()

    const exportButton = screen.getByText('Export').closest('button')
    expect(exportButton).toBeDisabled()
    expect(exportButton).toHaveAttribute(
      'title',
      'Add at least one source to this knowledge base first',
    )
  }, 30000)

  it('enables Export once a source exists', async () => {
    detail.current = makeDetail({
      status: 'ready',
      total_sources: 1,
      sources: [{
        uuid: 'src-1',
        source_type: 'url',
        url: 'https://example.gov/rule',
        url_title: 'A Rule',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
      }],
    })
    await openDetail()

    expect(screen.getByText('Export').closest('button')).not.toBeDisabled()
  }, 30000)

  // Support ticket: evaluators needed refresh/ingestion provenance per source
  // to verify currency without comparing every source to its original.
  it('shows what is served when the last refresh failed, and the content hash', async () => {
    detail.current = makeDetail({
      can_manage: true,
      sources: [{
        uuid: 'src-1',
        source_type: 'url',
        url: 'https://example.gov/rule',
        url_title: 'A Rule',
        status: 'ready',
        chunk_count: 4,
        created_at: '2026-01-01T00:00:00Z',
        processed_at: '2026-06-24T09:00:00Z',
        error_message: 'Refresh failed — previous content kept: HTTP 503',
        currency: {
          status: 'retained_previous',
          last_refresh_attempted_at: '2026-08-27T15:30:00Z',
          last_retrieved_at: '2026-06-24T09:00:00Z',
          last_ingested_at: '2026-06-24T09:00:00Z',
          content_retrieved_at: '2026-06-24T09:00:00Z',
          content_hash: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
          content_hash_algorithm: 'sha256',
          content_hash_recorded: true,
          last_refresh_outcome: 'retrieval_failed',
          last_refresh_error: 'HTTP 503',
        },
      }],
    })
    await openDetail()

    const line = screen.getByTestId('source-currency')
    expect(line.textContent).toContain('4 chunks')
    expect(line.textContent).toContain('Refresh failed')
    expect(line.textContent).toContain('serving text from')
    expect(line.textContent).toContain('abcdef012345')
  }, 30000)
})
