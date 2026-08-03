import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ExploreTab } from './ExploreTab'
import type { VerifiedCatalogItem } from '../../types/library'

const navigateMock = vi.hoisted(() => vi.fn())
const invalidateQueriesMock = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: invalidateQueriesMock }),
}))

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../api/library', () => ({
  listVerifiedItems: vi.fn(),
  browseCollections: vi.fn().mockResolvedValue({ collections: [] }),
  listFeaturedCollections: vi.fn().mockResolvedValue({ collections: [] }),
  listLibraries: vi.fn().mockResolvedValue([]),
}))

vi.mock('../../api/knowledge', () => ({
  adoptKnowledgeBase: vi.fn(),
}))

vi.mock('../../api/teams', () => ({
  listTeams: vi.fn().mockResolvedValue([]),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'viewer', email: 'viewer@example.com', name: 'Viewer', is_admin: false },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    activeProjectUuid: null,
    activeProjectTitle: null,
    activeProjectRole: null,
  }),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

vi.mock('../../lib/shareLink', () => ({
  useShareLink: () => vi.fn(),
  buildShareUrl: vi.fn(),
}))

import { listVerifiedItems } from '../../api/library'
import { adoptKnowledgeBase } from '../../api/knowledge'

function makeItem(overrides: Partial<VerifiedCatalogItem> = {}): VerifiedCatalogItem {
  return {
    id: 'cat-1',
    item_id: 'wf-1',
    kind: 'workflow',
    name: 'Budget Analyzer',
    tags: [],
    verified: true,
    created_at: '2026-01-01T00:00:00',
    display_name: null,
    description: null,
    markdown: null,
    organization_ids: [],
    quality_score: 85,
    quality_tier: 'silver',
    quality_grade: 'B',
    last_validated_at: null,
    validation_run_count: 0,
    source_uuid: 'wf-uuid-1',
    ...overrides,
  }
}

async function openItemFromCatalog(item: VerifiedCatalogItem) {
  vi.mocked(listVerifiedItems).mockResolvedValue({ items: [item], total: 1 })
  render(<ExploreTab />)
  // Card click opens the detail modal; "Open" inside it triggers navigation.
  fireEvent.click(await screen.findByText(item.name))
  fireEvent.click(await screen.findByRole('button', { name: 'Open' }))
}

describe('ExploreTab open navigation', () => {
  beforeEach(() => {
    navigateMock.mockClear()
  })

  it('keeps tab=library when opening a verified workflow, so closing returns to Explore', async () => {
    await openItemFromCatalog(makeItem())
    expect(navigateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/',
        search: expect.objectContaining({ tab: 'library', workflow: 'wf-uuid-1' }),
      }),
    )
  })

  it('disables Open in Chat for a knowledge base with zero indexed chunks', async () => {
    vi.mocked(listVerifiedItems).mockResolvedValue({
      items: [makeItem({
        id: 'cat-kb-0',
        item_id: 'kb-1',
        kind: 'knowledge_base',
        name: 'Empty Regs KB',
        source_uuid: 'kb-uuid-1',
        total_chunks: 0,
      })],
      total: 1,
    })
    render(<ExploreTab />)
    fireEvent.click(await screen.findByText('Empty Regs KB'))

    expect(await screen.findByRole('button', { name: 'Open in Chat' })).toBeDisabled()
    // Disabled buttons can't be hovered by keyboard/touch users, so the reason
    // is also stated visibly.
    expect(screen.getByText(/no indexed content yet/)).toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('keeps Open in Chat enabled for a knowledge base with indexed chunks', async () => {
    vi.mocked(listVerifiedItems).mockResolvedValue({
      items: [makeItem({
        id: 'cat-kb-1',
        item_id: 'kb-2',
        kind: 'knowledge_base',
        name: 'Export Control KB',
        source_uuid: 'kb-uuid-2',
        total_chunks: 120,
      })],
      total: 1,
    })
    render(<ExploreTab />)
    fireEvent.click(await screen.findByText('Export Control KB'))

    expect(await screen.findByRole('button', { name: 'Open in Chat' })).not.toBeDisabled()
    expect(screen.queryByText(/no indexed content yet/)).not.toBeInTheDocument()
  })

  it('keeps tab=library when opening a verified extraction', async () => {
    await openItemFromCatalog(makeItem({
      id: 'cat-2',
      item_id: 'ss-1',
      kind: 'search_set',
      name: 'Award Terms Extractor',
      source_uuid: 'ss-uuid-1',
    }))
    expect(navigateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/',
        search: expect.objectContaining({ tab: 'library', extraction: 'ss-uuid-1' }),
      }),
    )
  })
})

describe('ExploreTab KB adopt', () => {
  beforeEach(() => {
    invalidateQueriesMock.mockClear()
    vi.mocked(adoptKnowledgeBase).mockClear()
  })

  it('invalidates the cached KB lists after adopting, so My KBs updates without a reload', async () => {
    vi.mocked(adoptKnowledgeBase).mockResolvedValue({} as never)
    vi.mocked(listVerifiedItems).mockResolvedValue({
      items: [makeItem({
        id: 'cat-kb-2',
        item_id: 'kb-3',
        kind: 'knowledge_base',
        name: 'Uniform Guidance KB',
        source_uuid: 'kb-uuid-3',
        total_chunks: 50,
      })],
      total: 1,
    })
    render(<ExploreTab />)
    fireEvent.click(await screen.findByText('Uniform Guidance KB'))
    fireEvent.click(await screen.findByRole('button', { name: /Add to My Knowledge Bases/ }))

    await vi.waitFor(() => {
      expect(adoptKnowledgeBase).toHaveBeenCalledWith('kb-uuid-3', undefined, undefined)
      expect(invalidateQueriesMock).toHaveBeenCalledWith({ queryKey: ['knowledgeBases'] })
    })
  })

  it('does not invalidate the KB list caches when adopting fails', async () => {
    vi.mocked(adoptKnowledgeBase).mockRejectedValue(new Error('nope'))
    vi.mocked(listVerifiedItems).mockResolvedValue({
      items: [makeItem({
        id: 'cat-kb-3',
        item_id: 'kb-4',
        kind: 'knowledge_base',
        name: 'Failing KB',
        source_uuid: 'kb-uuid-4',
        total_chunks: 50,
      })],
      total: 1,
    })
    render(<ExploreTab />)
    fireEvent.click(await screen.findByText('Failing KB'))
    fireEvent.click(await screen.findByRole('button', { name: /Add to My Knowledge Bases/ }))

    await vi.waitFor(() => {
      expect(adoptKnowledgeBase).toHaveBeenCalled()
    })
    expect(invalidateQueriesMock).not.toHaveBeenCalled()
  })
})
