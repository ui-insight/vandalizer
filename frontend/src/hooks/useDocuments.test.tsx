import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode } from 'react'

const mockListContents = vi.fn()

vi.mock('../api/documents', () => ({
  listContents: (...args: unknown[]) => mockListContents(...args),
}))

import { useDocuments } from './useDocuments'

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

describe('useDocuments', () => {
  it('returns empty arrays while loading', () => {
    mockListContents.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useDocuments(null), { wrapper: createWrapper() })

    expect(result.current.loading).toBe(true)
    expect(result.current.documents).toEqual([])
    expect(result.current.folders).toEqual([])
  })

  it('returns documents and folders after loading', async () => {
    const data = {
      documents: [{ id: '1', title: 'Doc1', uuid: 'd1', extension: 'pdf' }],
      folders: [{ id: '2', title: 'Folder1', uuid: 'f1' }],
    }
    mockListContents.mockResolvedValueOnce(data)

    const { result } = renderHook(() => useDocuments(null), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.documents).toEqual(data.documents)
    expect(result.current.folders).toEqual(data.folders)
  })

  it('passes folderId and teamUuid to API', async () => {
    mockListContents.mockResolvedValueOnce({ documents: [], folders: [] })

    const { result } = renderHook(() => useDocuments('folder-123', 'team-abc'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockListContents).toHaveBeenCalledWith('folder-123', 'team-abc')
  })

  it('passes undefined folderId when null', async () => {
    mockListContents.mockResolvedValueOnce({ documents: [], folders: [] })

    const { result } = renderHook(() => useDocuments(null), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockListContents).toHaveBeenCalledWith(undefined, undefined)
  })

  it('provides a refresh function', async () => {
    mockListContents.mockResolvedValue({ documents: [], folders: [] })

    const { result } = renderHook(() => useDocuments(null), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(typeof result.current.refresh).toBe('function')
  })

  it('returns stable array references when loading', () => {
    mockListContents.mockReturnValue(new Promise(() => {}))

    const { result, rerender } = renderHook(() => useDocuments(null), {
      wrapper: createWrapper(),
    })

    const docs1 = result.current.documents
    const folders1 = result.current.folders
    rerender()
    // Should be the same reference (stable fallbacks)
    expect(result.current.documents).toBe(docs1)
    expect(result.current.folders).toBe(folders1)
  })
})
