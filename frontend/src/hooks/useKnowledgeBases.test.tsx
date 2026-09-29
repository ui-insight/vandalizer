import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { useScopedKnowledgeBases } from './useKnowledgeBases'
import type { KnowledgeBase } from '../types/knowledge'
const auth = vi.hoisted(() => ({ user: { user_id: 'alice', current_team: 'team-a' } }))
const list = vi.hoisted(() => vi.fn())
vi.mock('./useAuth', () => ({ useAuth: () => auth }))
vi.mock('../api/knowledge', () => ({ listKnowledgeBasesV2: list }))
const row = (uuid: string) => ({ uuid, status: 'ready' }) as KnowledgeBase
function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
beforeEach(() => { list.mockReset(); auth.user = { user_id: 'alice', current_team: 'team-a' } })
it('loads later pages before project filtering and local sorting', async () => {
  list.mockResolvedValueOnce({ items: [row('first')], total: 2 }).mockResolvedValueOnce({ items: [row('pinned-later')], total: 2 })
  const { result } = renderHook(() => useScopedKnowledgeBases({ scope: 'mine' }), { wrapper: wrapper() })
  await waitFor(() => expect(result.current.knowledgeBases.map(k => k.uuid)).toEqual(['first', 'pinned-later']))
  expect(list).toHaveBeenLastCalledWith({ scope: 'mine', skip: 1, limit: 200 })
})
it('never shows cached rows from another account or team while the next request is pending', async () => {
  list.mockResolvedValueOnce({ items: [row('alice-a')], total: 1 })
  const { result, rerender } = renderHook(() => useScopedKnowledgeBases({ scope: 'team' }), { wrapper: wrapper() })
  await waitFor(() => expect(result.current.knowledgeBases[0]?.uuid).toBe('alice-a'))
  list.mockImplementation(() => new Promise(() => {}))
  auth.user = { user_id: 'alice', current_team: 'team-b' }; rerender()
  expect(result.current.knowledgeBases).toEqual([])
  auth.user = { user_id: 'bob', current_team: 'team-a' }; rerender()
  expect(result.current.knowledgeBases).toEqual([])
})
it('surfaces a later-page failure rather than presenting a partial list as complete', async () => {
  list.mockResolvedValueOnce({ items: [row('first')], total: 2 }).mockRejectedValueOnce(new Error('offline'))
  const { result } = renderHook(() => useScopedKnowledgeBases({ scope: 'mine' }), { wrapper: wrapper() })
  await waitFor(() => expect(result.current.error?.message).toBe('offline'))
  expect(result.current.knowledgeBases).toEqual([])
})
