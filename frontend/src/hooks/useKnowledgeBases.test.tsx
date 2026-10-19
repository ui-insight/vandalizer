/**
 * Support ticket: the KB page showed no count anywhere, unlike Automations
 * and Projects. useKBTabCounts feeds the counts on the My KBs / Team /
 * Everyone tabs.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useKBTabCounts } from './useKnowledgeBases'

vi.mock('../api/knowledge', () => ({
  listKnowledgeBasesV2: vi.fn(async (params?: { scope?: string }) => (
    params?.scope === 'team'
      ? { items: [{ uuid: 'team-1', is_reference: false }], total: 1 }
      : {
          // One page of 50 would be the real shape; the total is what counts.
          items: [
            { uuid: 'own-1', is_reference: false },
            { uuid: 'ref-row', is_reference: true, source_kb_uuid: 'catalog-1' },
          ],
          total: 61,
        }
  )),
}))
vi.mock('../api/library', () => ({
  listVerifiedItems: vi.fn(async () => ({ items: [{}], total: 40 })),
}))

import { listVerifiedItems } from '../api/library'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useKBTabCounts', () => {
  it('reports each tab total, null until loaded', async () => {
    const { result } = renderHook(() => useKBTabCounts(), { wrapper })
    expect(result.current).toEqual({ mine: null, team: null, explore: null })

    await waitFor(() => expect(result.current).toEqual({ mine: 61, team: 1, explore: 40 }))
    // The Everyone count asks the catalog for a total, not a page of items.
    expect(listVerifiedItems).toHaveBeenCalledWith({ kind: 'knowledge_base', limit: 1 })
  })

  it('counts only pinned KBs while scoped to a project, matching a bookmark by its source', async () => {
    const pinned = new Set(['catalog-1', 'team-1'])
    const { result } = renderHook(() => useKBTabCounts(pinned), { wrapper })

    await waitFor(() => expect(result.current).toEqual({ mine: 1, team: 1, explore: 40 }))
  })
})
