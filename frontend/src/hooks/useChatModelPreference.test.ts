import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getUserConfig, updateUserConfig } from '../api/config'
import { useChatModelPreference } from './useChatModelPreference'
vi.mock('../api/config', () => ({ getUserConfig: vi.fn(), updateUserConfig: vi.fn() }))
beforeEach(() => { vi.resetAllMocks(); vi.mocked(getUserConfig).mockResolvedValue({ model: 'old', available_models: [], temperature: .2, top_p: 1 }) })
it('keeps a deliberate selection when the saved preference arrives late', async () => {
  let loaded!: (config: Awaited<ReturnType<typeof getUserConfig>>) => void
  vi.mocked(getUserConfig).mockImplementation(() => new Promise(resolve => { loaded = resolve }))
  const { result } = renderHook(() => useChatModelPreference())
  act(() => result.current.select('chosen'))
  await act(async () => loaded({ model: 'late-default', available_models: [], temperature: .2, top_p: 1 }))
  expect(result.current.selectedModel).toBe('chosen')
})
it('serializes rapid default changes and retries the exact failed choice without reverting the chat', async () => {
  let finish!: () => void
  vi.mocked(updateUserConfig).mockImplementationOnce(() => new Promise(resolve => { finish = () => resolve({ model: 'first', available_models: [], temperature: .2, top_p: 1 }) })).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ model: 'second', available_models: [], temperature: .2, top_p: 1 })
  const { result } = renderHook(() => useChatModelPreference())
  await waitFor(() => expect(result.current.selectedModel).toBe('old'))
  act(() => { result.current.select('first'); result.current.select('second') })
  await waitFor(() => expect(updateUserConfig).toHaveBeenCalledTimes(1))
  await act(async () => finish())
  await waitFor(() => expect(result.current.error).toContain('Could not save'))
  expect(result.current.selectedModel).toBe('second')
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.error).toBeNull())
  expect(vi.mocked(updateUserConfig).mock.calls.map(call => call[0])).toEqual([{ model: 'first' }, { model: 'second' }, { model: 'second' }])
})
it('keeps a load failure actionable and recovers the saved model on retry', async () => {
  vi.mocked(getUserConfig).mockRejectedValueOnce(new Error('offline'))
  const { result } = renderHook(() => useChatModelPreference())
  await waitFor(() => expect(result.current.error).toContain('Could not load'))
  act(() => result.current.retry())
  await waitFor(() => expect(result.current.selectedModel).toBe('old'))
})
