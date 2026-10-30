/** Every catalog KB appears on the Explore landing, however many are top rated.
 *
 *  Support ticket: DOE Financial Assistance, DOD/DFARS and FAR were in the
 *  catalog but not on Knowledge Bases → Everyone. The "Top Rated" spotlight
 *  showed the first six excellent-tier items and the main grid dropped every
 *  excellent-tier item, so the seventh and later showed nowhere. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { VerifiedCatalogItem } from '../../types/library'

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }) }))
vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../api/library', () => ({
  listVerifiedItems: vi.fn(),
  browseCollections: vi.fn().mockResolvedValue({ collections: [] }),
  listFeaturedCollections: vi.fn().mockResolvedValue({ collections: [] }),
  listLibraries: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../api/knowledge', () => ({ adoptKnowledgeBase: vi.fn() }))
vi.mock('../../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([]) }))
vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: '1', user_id: 'viewer', email: 'v@example.com', name: 'V', is_admin: false }, loading: false }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ activateKB: vi.fn(), activeProjectUuid: null, activeProjectTitle: null, activeProjectRole: null }),
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../lib/shareLink', () => ({ useShareLink: () => vi.fn(), buildShareUrl: vi.fn() }))

import { listVerifiedItems } from '../../api/library'
import { KBExploreTab } from './KBExploreTab'
import { SPOTLIGHT_SIZE, splitSpotlight } from '../library/useCatalogBrowser'

// The bundled catalog: ten ship excellent, one good.
const CATALOG: [string, 'excellent' | 'good'][] = [
  ['Uniform Guidance (2 CFR 200)', 'excellent'],
  ['NSF PAPPG', 'excellent'],
  ['NIH Grants Policy Statement', 'excellent'],
  ['Common Rule', 'excellent'],
  ['Financial Conflict of Interest', 'excellent'],
  ['Export Control', 'excellent'],
  ['UI Sponsored Programs', 'excellent'],
  ['DOE Financial Assistance Rules', 'excellent'],
  ['DOD Research Funding & DFARS', 'excellent'],
  ['Federal Acquisition Regulation (FAR)', 'excellent'],
  ['Responsible Conduct of Research', 'good'],
]

const item = (i: number, name: string, tier: string): VerifiedCatalogItem => ({
  id: `cat-${i}`, item_id: `kb-${i}`, kind: 'knowledge_base', name, tags: [], verified: true,
  created_at: '2026-01-01T00:00:00', display_name: null, description: null, markdown: null,
  organization_ids: [], quality_score: 90, quality_tier: tier, quality_grade: 'A',
  last_validated_at: null, validation_run_count: 0, source_uuid: `kb-uuid-${i}`,
  quality_asserted: false,
} as VerifiedCatalogItem)

const items = CATALOG.map(([name, tier], i) => item(i, name, tier))

describe('KBExploreTab landing', () => {
  it('shows every catalog KB exactly once when more than six are top rated', async () => {
    vi.mocked(listVerifiedItems).mockResolvedValue({ items, total: items.length })
    render(<KBExploreTab />)

    await screen.findByRole('heading', { name: 'Strong on tested examples' })
    for (const [name] of CATALOG) {
      expect(screen.getAllByText(name), name).toHaveLength(1)
    }
    // The count names every excellent item, not just the six on show.
    expect(screen.getByText('11 items with strong measured results')).toBeTruthy()
  })
})

describe('splitSpotlight', () => {
  it('puts each item in exactly one section', () => {
    const { spotlight, rest, topRatedCount } = splitSpotlight(items)
    expect(spotlight).toHaveLength(SPOTLIGHT_SIZE)
    expect(topRatedCount).toBe(11)
    expect(rest.map(i => i.name)).toEqual(expect.arrayContaining([
      'DOE Financial Assistance Rules', 'DOD Research Funding & DFARS',
      'Federal Acquisition Regulation (FAR)', 'Responsible Conduct of Research',
    ]))
    expect(new Set([...spotlight, ...rest].map(i => i.id)).size).toBe(items.length)
    expect(spotlight.length + rest.length).toBe(items.length)
  })

  it('leads the spotlight with measured ratings over seeded ones', () => {
    const measured = { ...items[9], quality_asserted: false }
    const { spotlight, rest } = splitSpotlight([...items.slice(0, 9).map(item => ({ ...item, quality_score: null, quality_asserted: true })), measured])
    expect(spotlight).toHaveLength(1)
    expect(rest).toHaveLength(9)
    expect(spotlight[0].name).toBe('Federal Acquisition Regulation (FAR)')
  })
})
