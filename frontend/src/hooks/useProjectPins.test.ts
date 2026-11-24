import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useProjectPins } from './useProjectPins'
import { listProjectPins, addProjectPin } from '../api/projects'
import type { ProjectPin } from '../types/project'
vi.mock('../api/projects', () => ({ listProjectPins: vi.fn(), addProjectPin: vi.fn(), removeProjectPin: vi.fn() }))
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
const pin = (target_id: string) => ({ pin_type: 'automation', target_id } as ProjectPin)
beforeEach(() => { vi.mocked(listProjectPins).mockReset(); vi.mocked(addProjectPin).mockReset() })
describe('project pin scope isolation', () => {
  it('ignores an older project response after switching', async () => {
    const a = pending<ProjectPin[]>()
    vi.mocked(listProjectPins).mockReturnValueOnce(a.promise).mockResolvedValueOnce([pin('b')])
    const { result, rerender } = renderHook(({ id }) => useProjectPins(id), { initialProps: { id: 'A' } })
    rerender({ id: 'B' }); await waitFor(() => expect(result.current.isPinned('automation', 'b')).toBe(true))
    await act(async () => a.resolve([pin('a')]))
    expect(result.current.isPinned('automation', 'a')).toBe(false)
    expect(result.current.isPinned('automation', 'b')).toBe(true)
  })
  it('preserves the current list on failure and retries', async () => {
    vi.mocked(listProjectPins).mockResolvedValueOnce([pin('a')]).mockRejectedValueOnce(new Error('Pins unavailable')).mockResolvedValueOnce([pin('b')])
    const { result } = renderHook(() => useProjectPins('A'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { await result.current.refresh() })
    expect(result.current.error).toBe('Pins unavailable'); expect(result.current.isPinned('automation', 'a')).toBe(true)
    await act(async () => { await result.current.refresh() })
    expect(result.current.error).toBeNull(); expect(result.current.isPinned('automation', 'b')).toBe(true)
  })
  it('does not let a late pin mutation refresh an old project over the new one', async () => {
    const mutation = pending<{ ok: boolean }>(); vi.mocked(addProjectPin).mockReturnValue(mutation.promise)
    vi.mocked(listProjectPins).mockResolvedValueOnce([pin('a')]).mockResolvedValueOnce([pin('b')])
    const { result, rerender } = renderHook(({ id }) => useProjectPins(id), { initialProps: { id: 'A' } })
    await waitFor(() => expect(result.current.loading).toBe(false))
    let update!: Promise<void>; act(() => { update = result.current.pin('automation', 'new-a') })
    rerender({ id: 'B' }); await waitFor(() => expect(result.current.isPinned('automation', 'b')).toBe(true))
    await act(async () => { mutation.resolve({ ok: true }); await update })
    expect(vi.mocked(listProjectPins).mock.calls).toEqual([['A'], ['B']])
    expect(result.current.isPinned('automation', 'b')).toBe(true)
  })
})
