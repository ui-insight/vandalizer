import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
const get = vi.fn()
vi.mock('../api/folders', () => ({ getBreadcrumbs: (...args: unknown[]) => get(...args) }))
import { useBreadcrumbs } from './useFolders'
beforeEach(() => { get.mockReset() })
it('announces path failure and retries without an unhandled rejection', async () => {
  get.mockRejectedValueOnce(new Error('Folder unavailable')).mockResolvedValue([{ uuid: 'a', title: 'Project' }])
  const { result } = renderHook(() => useBreadcrumbs('a'))
  await waitFor(() => expect(result.current.error).toBe('Folder unavailable'))
  await act(() => result.current.refresh())
  expect(result.current.error).toBeNull()
  expect(result.current.breadcrumbs[0].title).toBe('Project')
})
it('ignores a late path response from the previous folder', async () => {
  let resolve!: (value: unknown) => void
  get.mockImplementationOnce(() => new Promise(r => { resolve = r })).mockResolvedValue([{ uuid: 'b', title: 'New folder' }])
  const { result, rerender } = renderHook(({ folder }) => useBreadcrumbs(folder), { initialProps: { folder: 'a' } })
  rerender({ folder: 'b' })
  await waitFor(() => expect(result.current.breadcrumbs[0]?.uuid).toBe('b'))
  await act(async () => resolve([{ uuid: 'a', title: 'Old folder' }]))
  expect(result.current.breadcrumbs[0].uuid).toBe('b')
})
