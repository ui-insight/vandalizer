import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { updateTestCase } from '../api/extractions'
import { useTestCaseSave } from './useTestCaseSave'

vi.mock('../api/extractions', () => ({ updateTestCase: vi.fn() }))
const update = vi.mocked(updateTestCase)
beforeEach(() => update.mockReset())

describe('test-case save recovery', () => {
  it('serializes and coalesces edits while an older request is in flight', async () => {
    let finish!: () => void
    update.mockImplementationOnce(() => new Promise(resolve => { finish = () => resolve({} as never) }))
    update.mockResolvedValue({} as never)
    const { result } = renderHook(useTestCaseSave)
    act(() => { void result.current.save('source', { source_text: 'first' }) })
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    act(() => {
      void result.current.save('source', { source_text: 'second' })
      void result.current.save('source', { source_text: 'latest', expected_values: { amount: '42' } })
    })
    expect(update).toHaveBeenCalledTimes(1)
    await act(async () => { finish(); await result.current.retry() })
    expect(update).toHaveBeenCalledTimes(2)
    expect(update).toHaveBeenLastCalledWith('source', { source_text: 'latest', expected_values: { amount: '42' } })
    expect(result.current.saving).toBe(false)
  })

  it('retains failed edits for retry and does not clear their error when another source saves', async () => {
    update.mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({} as never)
    const { result } = renderHook(useTestCaseSave)
    await act(async () => { expect(await result.current.save('failed', { expected_values: { amount: '42' } })).toBe(false) })
    await act(async () => { await result.current.save('other', { source_text: 'saved' }) })
    expect(result.current.error).toContain('Offline')
    await act(async () => { expect(await result.current.retry()).toBe(true) })
    expect(update).toHaveBeenLastCalledWith('failed', { expected_values: { amount: '42' } })
    expect(result.current.error).toBeNull()
  })
})
