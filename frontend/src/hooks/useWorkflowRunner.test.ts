import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const runWorkflow = vi.fn()
vi.mock('../api/workflows', () => ({
  runWorkflow: (...args: unknown[]) => runWorkflow(...args),
  getWorkflowStatus: vi.fn(() => new Promise(() => {})),
  getBatchStatus: vi.fn(() => new Promise(() => {})),
  cancelWorkflow: vi.fn(),
  cancelBatch: vi.fn(),
}))
vi.mock('../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({ bumpActivitySignal: vi.fn(), openWorkflowShareToken: null }),
}))

const { useWorkflowRunner } = await import('./useWorkflowRunner')

afterEach(() => runWorkflow.mockReset())

describe('useWorkflowRunner.start and ticked folders', () => {
  it('sends folder_uuids with the run when folders are ticked', async () => {
    runWorkflow.mockResolvedValue({ session_id: 's1', activity_id: 'a1' })
    const { result, unmount } = renderHook(() => useWorkflowRunner())
    await act(() => result.current.start('wf1', ['D1'], undefined, false, undefined, ['F1', 'F2']))
    expect(runWorkflow).toHaveBeenCalledWith('wf1', expect.objectContaining({
      document_uuids: ['D1'], folder_uuids: ['F1', 'F2'],
    }), undefined)
    unmount()
  })

  it('omits folder_uuids when none are ticked or the run takes none', async () => {
    runWorkflow.mockResolvedValue({ session_id: 's1', activity_id: 'a1' })
    const { result, unmount } = renderHook(() => useWorkflowRunner())
    await act(() => result.current.start('wf1', [], undefined, false, undefined, []))
    await act(() => result.current.start('wf1', ['D1']))
    for (const [, body] of runWorkflow.mock.calls) expect(body).not.toHaveProperty('folder_uuids')
    unmount()
  })
})
