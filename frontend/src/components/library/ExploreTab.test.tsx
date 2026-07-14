import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ExploreTab } from './ExploreTab'
import type { VerifiedCatalogItem } from '../../types/library'

const navigateMock = vi.hoisted(() => vi.fn())

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
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
