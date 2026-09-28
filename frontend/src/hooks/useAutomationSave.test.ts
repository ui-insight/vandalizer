import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAutomationSave } from './useAutomationSave'
import { updateAutomation } from '../api/automations'
import type { Automation } from '../types/automation'
vi.mock('../api/automations', () => ({ updateAutomation: vi.fn() }))
const base = { id: 'auto-1', name: 'Review' } as Automation
beforeEach(() => { vi.clearAllMocks(); vi.mocked(updateAutomation).mockImplementation(async (_id, changes) => ({ ...base, ...changes } as Automation)) })
afterEach(() => vi.useRealTimers())

describe('automation autosave', () => {
  it('combines edits to different fields and flushes before closing', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useAutomationSave('auto-1', vi.fn()))
    act(() => { void result.current.save({ description: 'New description' }, true); void result.current.save({ trigger_config: { file_types: ['pdf'] } }, true) })
    expect(updateAutomation).not.toHaveBeenCalled()
    expect(result.current.state).toBe('pending')
    await act(async () => { expect(await result.current.flush()).toBe(true) })
    expect(updateAutomation).toHaveBeenCalledExactlyOnceWith('auto-1', { description: 'New description', trigger_config: { file_types: ['pdf'] } })
    expect(result.current.state).toBe('saved')
  })
  it('serializes writes and overlays newer edits on an older response', async () => {
    let release!: (value: Automation) => void
    vi.mocked(updateAutomation).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    const onSaved = vi.fn()
    const { result } = renderHook(() => useAutomationSave('auto-1', onSaved))
    act(() => { void result.current.save({ name: 'First' }); void result.current.save({ name: 'Newest' }) })
    expect(updateAutomation).toHaveBeenCalledTimes(1)
    await act(async () => { release({ ...base, name: 'First' }); await result.current.flush() })
    expect(updateAutomation).toHaveBeenNthCalledWith(2, 'auto-1', { name: 'Newest' })
    expect(onSaved.mock.calls.every(([value]) => value.name === 'Newest')).toBe(true)
  })
  it('retains failed edits for an explicit retry', async () => {
    vi.mocked(updateAutomation).mockRejectedValueOnce(new Error('Offline'))
    const { result } = renderHook(() => useAutomationSave('auto-1', vi.fn()))
    await act(async () => { expect(await result.current.save({ description: 'Keep this draft' })).toBe(false) })
    expect(result.current.state).toBe('error')
    expect(result.current.error).toBe('Offline')
    await act(async () => { expect(await result.current.flush()).toBe(true) })
    expect(updateAutomation).toHaveBeenNthCalledWith(2, 'auto-1', { description: 'Keep this draft' })
    expect(result.current.state).toBe('saved')
  })
  it('flushes a pending edit when navigation unmounts the editor', async () => {
    const onSaved = vi.fn()
    const { result, unmount } = renderHook(() => useAutomationSave('auto-1', onSaved))
    act(() => { void result.current.save({ description: 'Do not discard' }, true) })
    unmount()
    await waitFor(() => expect(updateAutomation).toHaveBeenCalledExactlyOnceWith('auto-1', { description: 'Do not discard' }))
    expect(onSaved).not.toHaveBeenCalled()
  })
})
