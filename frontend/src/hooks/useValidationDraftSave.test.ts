import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useValidationDraftSave } from './useValidationDraftSave'

afterEach(() => vi.useRealTimers())

describe('validation draft persistence', () => {
  it('flushes the latest debounced edit before a dependent run', async () => {
    vi.useFakeTimers()
    const persist = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useValidationDraftSave(persist))
    act(() => { result.current.save('first'); result.current.save('latest') })
    expect(persist).not.toHaveBeenCalled()
    await act(async () => { expect(await result.current.flush()).toBe(true) })
    expect(persist).toHaveBeenCalledExactlyOnceWith('latest')
    expect(result.current.saving).toBe(false)
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(persist).toHaveBeenCalledTimes(1)
  })

  it('serializes writes and waits for edits made during an in-flight request', async () => {
    let finish!: () => void
    const persist = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve })).mockResolvedValue(undefined)
    const { result } = renderHook(() => useValidationDraftSave(persist))
    let flush!: Promise<boolean>
    await act(async () => { result.current.save('first'); flush = result.current.flush(); await Promise.resolve() })
    act(() => { result.current.save('second'); result.current.save('latest') })
    expect(persist).toHaveBeenCalledTimes(1)
    await act(async () => { finish(); expect(await flush).toBe(true) })
    expect(persist.mock.calls).toEqual([['first'], ['latest']])
  })

  it('blocks dependent work on failure and retains the newest edit for retry', async () => {
    let reject!: (reason: Error) => void
    const persist = vi.fn().mockImplementationOnce(() => new Promise<void>((_, fail) => { reject = fail })).mockResolvedValue(undefined)
    const { result } = renderHook(() => useValidationDraftSave(persist))
    let flush!: Promise<boolean>
    await act(async () => { result.current.save('old'); flush = result.current.flush(); await Promise.resolve() })
    act(() => { result.current.save('corrected') })
    await act(async () => { reject(new Error('Offline')); expect(await flush).toBe(false) })
    expect(result.current.error).toBe('Offline')
    await act(async () => { expect(await result.current.flush()).toBe(true) })
    expect(persist.mock.calls).toEqual([['old'], ['corrected']])
    expect(result.current.error).toBeNull()
  })

  it('sends pending edits when the editor closes', async () => {
    vi.useFakeTimers()
    const persist = vi.fn().mockResolvedValue(undefined)
    const { result, unmount } = renderHook(() => useValidationDraftSave(persist))
    act(() => { result.current.save('last edit') })
    unmount()
    await act(async () => { await Promise.resolve() })
    expect(persist).toHaveBeenCalledExactlyOnceWith('last edit')
  })
})
