import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useAutomations } from './useAutomations'
import { listAutomations } from '../api/automations'
import type { Automation } from '../types/automation'
vi.mock('../api/automations', () => ({ listAutomations: vi.fn() }))
beforeEach(() => { vi.mocked(listAutomations).mockReset() })
it('retains the last successful list after a refresh error and retries', async () => {
  vi.mocked(listAutomations).mockResolvedValueOnce([{ id: 'a' } as Automation]).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce([{ id: 'b' } as Automation])
  const { result } = renderHook(() => useAutomations()); await waitFor(() => expect(result.current.loading).toBe(false))
  await act(async () => { await result.current.refresh() })
  expect(result.current.error).toBe('Offline'); expect(result.current.automations[0].id).toBe('a')
  await act(async () => { await result.current.refresh() })
  expect(result.current.error).toBeNull(); expect(result.current.automations[0].id).toBe('b')
})
it('ignores an earlier list response that finishes after a newer refresh', async () => {
  let resolve!: (value: Automation[]) => void
  vi.mocked(listAutomations).mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValueOnce([{ id: 'new' } as Automation])
  const { result } = renderHook(() => useAutomations())
  await act(async () => { await result.current.refresh() })
  await act(async () => { resolve([{ id: 'old' } as Automation]) })
  expect(result.current.automations[0].id).toBe('new'); expect(result.current.loading).toBe(false)
})
