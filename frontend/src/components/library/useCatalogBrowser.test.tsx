import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { browseCollections, listFeaturedCollections, listVerifiedItems } from '../../api/library'
import { useCatalogBrowser } from './useCatalogBrowser'
import type { VerifiedCatalogItem } from '../../types/library'
vi.mock('../../api/library', () => ({ browseCollections: vi.fn(), listFeaturedCollections: vi.fn(), listVerifiedItems: vi.fn() }))
const item = (id: string) => ({ id, name: id, quality_tier: 'good' } as VerifiedCatalogItem)
const page = (id: string, total = 1) => ({ items: [item(id)], total })
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
const options = { loadErrorMessage: 'Catalog unavailable', onLoadMoreError: vi.fn() }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(browseCollections).mockResolvedValue({ collections: [] }); vi.mocked(listFeaturedCollections).mockResolvedValue({ collections: [] }) })
describe('catalog query isolation', () => {
  it('ignores an older filter response', async () => {
    const old = deferred<ReturnType<typeof page>>()
    vi.mocked(listVerifiedItems).mockReturnValueOnce(old.promise).mockResolvedValue(page('filtered'))
    const { result } = renderHook(() => useCatalogBrowser(options))
    act(() => result.current.setQualityFilter('excellent'))
    await waitFor(() => expect(result.current.items[0]?.id).toBe('filtered'))
    await act(async () => old.resolve(page('old')))
    expect(result.current.items[0].id).toBe('filtered')
    expect(result.current.total).toBe(1)
  })
  it('blocks duplicate pagination and ignores a next page after changing kind', async () => {
    const next = deferred<ReturnType<typeof page>>()
    vi.mocked(listVerifiedItems).mockResolvedValueOnce(page('first', 2)).mockReturnValueOnce(next.promise).mockResolvedValue(page('knowledge'))
    const { result } = renderHook(() => useCatalogBrowser(options))
    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => { void result.current.handleLoadMore(); void result.current.handleLoadMore() })
    expect(listVerifiedItems).toHaveBeenCalledTimes(2)
    act(() => result.current.setKindFilter('knowledge_base'))
    await waitFor(() => expect(result.current.items[0]?.id).toBe('knowledge'))
    await act(async () => next.resolve(page('old-next')))
    expect(result.current.items.map(x => x.id)).toEqual(['knowledge'])
    expect(result.current.loadingMore).toBe(false)
  })
  it('keeps results on pagination failure and retries the same offset', async () => {
    vi.mocked(listVerifiedItems).mockResolvedValueOnce(page('first', 2)).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(page('second', 2))
    const { result } = renderHook(() => useCatalogBrowser(options))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => result.current.handleLoadMore())
    expect(result.current.items.map(x => x.id)).toEqual(['first'])
    expect(options.onLoadMoreError).toHaveBeenCalledWith(expect.stringContaining('preserved'))
    await act(async () => result.current.handleLoadMore())
    expect(result.current.items.map(x => x.id)).toEqual(['first', 'second'])
    expect(vi.mocked(listVerifiedItems).mock.calls.slice(1).map(call => call[0]?.skip)).toEqual([1, 1])
  })
  it('recovers collections separately from item loading', async () => {
    vi.mocked(browseCollections).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ collections: [] })
    vi.mocked(listVerifiedItems).mockResolvedValue(page('first'))
    const { result } = renderHook(() => useCatalogBrowser({ ...options, lockedKind: 'knowledge_base' }))
    await waitFor(() => expect(result.current.collectionsError).not.toBeNull())
    expect(result.current.error).toBeNull()
    await act(async () => result.current.retryCollections())
    expect(result.current.collectionsError).toBeNull()
    expect(browseCollections).toHaveBeenLastCalledWith('knowledge_base')
  })
})
