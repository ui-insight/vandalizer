import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useAdminQuery } from './useAdminQuery'

it('ignores an old request after a filter change and removes stale export data during retry', async () => {
  let finish!: (value: string) => void
  const slow = vi.fn(() => new Promise<string>(resolve => { finish = resolve }))
  const current = vi.fn<() => Promise<string>>().mockResolvedValueOnce('current').mockRejectedValueOnce(new Error('Unavailable')).mockResolvedValueOnce('recovered')
  const { result, rerender } = renderHook(({request}) => useAdminQuery(request), {initialProps:{request:slow as () => Promise<string>}})
  rerender({request:current})
  await waitFor(() => expect(result.current.data).toBe('current'))
  await act(async () => { finish('obsolete') })
  expect(result.current.data).toBe('current')
  act(() => result.current.load())
  expect(result.current.data).toBeNull()
  await waitFor(() => expect(result.current.error).toBe('Unavailable'))
  expect(result.current.loading).toBe(false)
  act(() => result.current.load())
  await waitFor(() => expect(result.current.data).toBe('recovered'))
  expect(result.current.error).toBeNull()
})
