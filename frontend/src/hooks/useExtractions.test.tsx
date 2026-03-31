import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode } from 'react'

const mockListSearchSets = vi.fn()
const mockCreateSearchSet = vi.fn()
const mockDeleteSearchSet = vi.fn()
const mockCloneSearchSet = vi.fn()
const mockListItems = vi.fn()
const mockAddItem = vi.fn()
const mockDeleteItem = vi.fn()
const mockUpdateItem = vi.fn()
const mockReorderItems = vi.fn()

vi.mock('../api/extractions', () => ({
  listSearchSets: (...args: unknown[]) => mockListSearchSets(...args),
  createSearchSet: (...args: unknown[]) => mockCreateSearchSet(...args),
  deleteSearchSet: (...args: unknown[]) => mockDeleteSearchSet(...args),
  cloneSearchSet: (...args: unknown[]) => mockCloneSearchSet(...args),
  listItems: (...args: unknown[]) => mockListItems(...args),
  addItem: (...args: unknown[]) => mockAddItem(...args),
  deleteItem: (...args: unknown[]) => mockDeleteItem(...args),
  updateItem: (...args: unknown[]) => mockUpdateItem(...args),
  reorderItems: (...args: unknown[]) => mockReorderItems(...args),
}))

import { useSearchSets, useSearchSetItems } from './useExtractions'

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useSearchSets', () => {
  it('returns empty array while loading', () => {
    mockListSearchSets.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useSearchSets(), { wrapper: createWrapper() })

    expect(result.current.loading).toBe(true)
    expect(result.current.searchSets).toEqual([])
  })

  it('returns search sets after loading', async () => {
    const sets = [
      { uuid: 'ss-1', title: 'Grant Fields' },
      { uuid: 'ss-2', title: 'Budget Fields' },
    ]
    mockListSearchSets.mockResolvedValueOnce(sets)

    const { result } = renderHook(() => useSearchSets(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.searchSets).toEqual(sets)
  })

  it('create calls API with title', async () => {
    mockListSearchSets.mockResolvedValue([])
    const newSet = { uuid: 'ss-new', title: 'New Set' }
    mockCreateSearchSet.mockResolvedValueOnce(newSet)

    const { result } = renderHook(() => useSearchSets(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let created: unknown
    await act(async () => {
      created = await result.current.create('New Set')
    })

    expect(mockCreateSearchSet).toHaveBeenCalledWith({ title: 'New Set' })
    expect(created).toEqual(newSet)
  })

  it('remove calls API with uuid', async () => {
    mockListSearchSets.mockResolvedValue([])
    mockDeleteSearchSet.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useSearchSets(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.remove('ss-1')
    })

    expect(mockDeleteSearchSet).toHaveBeenCalledWith('ss-1')
  })

  it('clone calls API with uuid', async () => {
    mockListSearchSets.mockResolvedValue([])
    const cloned = { uuid: 'ss-clone', title: 'Grant Fields (copy)' }
    mockCloneSearchSet.mockResolvedValueOnce(cloned)

    const { result } = renderHook(() => useSearchSets(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let result2: unknown
    await act(async () => {
      result2 = await result.current.clone('ss-1')
    })

    expect(mockCloneSearchSet).toHaveBeenCalledWith('ss-1')
    expect(result2).toEqual(cloned)
  })
})

describe('useSearchSetItems', () => {
  it('does not fetch when searchSetUuid is null', () => {
    const { result } = renderHook(() => useSearchSetItems(null), {
      wrapper: createWrapper(),
    })

    expect(result.current.items).toEqual([])
    expect(mockListItems).not.toHaveBeenCalled()
  })

  it('fetches items when searchSetUuid is provided', async () => {
    const items = [
      { id: 'item-1', searchphrase: 'PI Name' },
      { id: 'item-2', searchphrase: 'Award Amount' },
    ]
    mockListItems.mockResolvedValueOnce(items)

    const { result } = renderHook(() => useSearchSetItems('ss-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.items).toEqual(items)
    expect(mockListItems).toHaveBeenCalledWith('ss-1')
  })

  it('add calls API with searchphrase', async () => {
    mockListItems.mockResolvedValue([])
    const newItem = { id: 'item-new', searchphrase: 'Department' }
    mockAddItem.mockResolvedValueOnce(newItem)

    const { result } = renderHook(() => useSearchSetItems('ss-1'), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.add('Department')
    })

    expect(mockAddItem).toHaveBeenCalledWith('ss-1', { searchphrase: 'Department' })
  })

  it('add does nothing when searchSetUuid is null', async () => {
    const { result } = renderHook(() => useSearchSetItems(null), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.add('Test')
    })

    expect(mockAddItem).not.toHaveBeenCalled()
  })

  it('remove calls API with item id', async () => {
    mockListItems.mockResolvedValue([])
    mockDeleteItem.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useSearchSetItems('ss-1'), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.remove('item-1')
    })

    expect(mockDeleteItem).toHaveBeenCalledWith('item-1')
  })

  it('update calls API with item id and data', async () => {
    mockListItems.mockResolvedValue([])
    mockUpdateItem.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useSearchSetItems('ss-1'), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.update('item-1', { searchphrase: 'Updated Field' })
    })

    expect(mockUpdateItem).toHaveBeenCalledWith('item-1', { searchphrase: 'Updated Field' })
  })
})
