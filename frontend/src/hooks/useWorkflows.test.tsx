import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode } from 'react'

const mockListWorkflows = vi.fn()
const mockCreateWorkflow = vi.fn()
const mockDeleteWorkflow = vi.fn()
const mockDuplicateWorkflow = vi.fn()

vi.mock('../api/workflows', () => ({
  listWorkflows: (...args: unknown[]) => mockListWorkflows(...args),
  createWorkflow: (...args: unknown[]) => mockCreateWorkflow(...args),
  deleteWorkflow: (...args: unknown[]) => mockDeleteWorkflow(...args),
  duplicateWorkflow: (...args: unknown[]) => mockDuplicateWorkflow(...args),
}))

import { useWorkflows } from './useWorkflows'

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

describe('useWorkflows', () => {
  it('returns empty array while loading', () => {
    mockListWorkflows.mockReturnValue(new Promise(() => {}))
    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })

    expect(result.current.loading).toBe(true)
    expect(result.current.workflows).toEqual([])
  })

  it('returns workflows after loading', async () => {
    const workflows = [
      { id: 'wf-1', name: 'Extract PI', steps: [] },
      { id: 'wf-2', name: 'Budget Review', steps: [] },
    ]
    mockListWorkflows.mockResolvedValueOnce({ items: workflows, total: 2, skip: 0, limit: 500 })

    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.workflows).toEqual(workflows)
    expect(result.current.total).toBe(2)
    expect(result.current.hasMore).toBe(false)
  })

  it('passes search and paging to the API instead of filtering locally', async () => {
    mockListWorkflows.mockResolvedValueOnce({ items: [], total: 0, skip: 40, limit: 20 })

    const { result } = renderHook(
      () => useWorkflows({ search: 'budget', skip: 40, limit: 20 }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockListWorkflows).toHaveBeenCalledWith({ search: 'budget', skip: 40, limit: 20 })
  })

  it('reports hasMore when the server holds matches this page omits', async () => {
    // The silent truncation that made workflows past the cap read as deleted.
    mockListWorkflows.mockResolvedValueOnce({
      items: [{ id: 'wf-1', name: 'Extract PI', steps: [] }],
      total: 412,
      skip: 0,
      limit: 1,
    })

    const { result } = renderHook(() => useWorkflows({ limit: 1 }), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.total).toBe(412)
    expect(result.current.hasMore).toBe(true)
  })

  it('create calls API and returns result', async () => {
    mockListWorkflows.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 500 })
    const newWf = { id: 'wf-new', name: 'New Workflow' }
    mockCreateWorkflow.mockResolvedValueOnce(newWf)

    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let created: unknown
    await act(async () => {
      created = await result.current.create('New Workflow')
    })

    expect(mockCreateWorkflow).toHaveBeenCalledWith({ name: 'New Workflow' })
    expect(created).toEqual(newWf)
  })

  it('remove calls API with workflow id', async () => {
    mockListWorkflows.mockResolvedValue([{ id: 'wf-1', name: 'Test' }])
    mockDeleteWorkflow.mockResolvedValueOnce(undefined)

    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.remove('wf-1')
    })

    expect(mockDeleteWorkflow).toHaveBeenCalledWith('wf-1')
  })

  it('duplicate calls API with workflow id', async () => {
    mockListWorkflows.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 500 })
    const duplicated = { id: 'wf-dup', name: 'Test (copy)' }
    mockDuplicateWorkflow.mockResolvedValueOnce(duplicated)

    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let dup: unknown
    await act(async () => {
      dup = await result.current.duplicate('wf-1')
    })

    expect(mockDuplicateWorkflow).toHaveBeenCalledWith('wf-1')
    expect(dup).toEqual(duplicated)
  })

  it('provides a refresh function', async () => {
    mockListWorkflows.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 500 })

    const { result } = renderHook(() => useWorkflows(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(typeof result.current.refresh).toBe('function')
  })
})
