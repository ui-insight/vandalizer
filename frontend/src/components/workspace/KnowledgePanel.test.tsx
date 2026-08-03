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

vi.mock('../../api/knowledge', () => ({
  getKnowledgeBase: (uuid: string) => getKnowledgeBase(uuid),
  getKBQuality: vi.fn().mockResolvedValue({}),
  getKBSourceHealth: vi.fn().mockResolvedValue({}),
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
    expect(screen.getByLabelText('Remove source')).toBeInTheDocument()
    expect(screen.getByText('Share with Team').closest('button')).not.toBeDisabled()
  }, 30000)
})
