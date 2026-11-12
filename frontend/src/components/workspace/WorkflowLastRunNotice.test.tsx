import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getWorkflowHistory, getWorkflowStatus, runWorkflow, type RunHistoryEntry } from '../../api/workflows'
import { useLastWorkflowRun } from '../../hooks/useLastWorkflowRun'
import { useWorkflowRunner } from '../../hooks/useWorkflowRunner'
import type { WorkflowStatus } from '../../types/workflow'
import { WorkflowLastRunNotice } from './WorkflowLastRunNotice'

vi.mock('../../api/workflows', () => ({ getWorkflowHistory: vi.fn(), getWorkflowStatus: vi.fn(), runWorkflow: vi.fn(), getBatchStatus: vi.fn(), cancelBatch: vi.fn(), cancelWorkflow: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ bumpActivitySignal: vi.fn(), openWorkflowShareToken: null }) }))
const last = { id: 'a', session_id: 'persisted-run', status: 'completed', started_at: '2026-10-29T22:28:00Z', finished_at: '2026-10-29T22:29:00Z' } as RunHistoryEntry
const output = { status: 'completed', final_output: { output: 'Saved review results' }, steps_output: { Review: { output: 'Saved step results' } } } as unknown as WorkflowStatus

function EditorRun() {
  const history = useLastWorkflowRun('workflow-1')
  const runner = useWorkflowRunner()
  return <>
    {!runner.sessionId && <WorkflowLastRunNotice run={history.lastRun} error={history.error} onRetry={history.retry} onShow={runner.loadSession} />}
    {runner.status && <div role="status">{String((runner.status.final_output as { output: string })?.output)}</div>}
  </>
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getWorkflowHistory).mockResolvedValue({ runs: [last] })
  vi.mocked(getWorkflowStatus).mockResolvedValue(output)
})

describe('reopening the editor after a refresh', () => {
  it('offers the persisted last run and opens its full output without rerunning', async () => {
    const first = render(<EditorRun />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show last run' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved review results')
    first.unmount()
    render(<EditorRun />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show last run' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved review results')
    expect(getWorkflowHistory).toHaveBeenCalledWith('workflow-1', 1)
    expect(getWorkflowStatus).toHaveBeenLastCalledWith('persisted-run', undefined)
    expect(runWorkflow).not.toHaveBeenCalled()
  })

  it('retains the reopen action if loading the per-step preview fails', async () => {
    vi.mocked(getWorkflowStatus).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(output)
    render(<EditorRun />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show last run' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved review results')
  })

  it('allows another attempt after opening the saved run fails', async () => {
    vi.mocked(getWorkflowStatus).mockResolvedValueOnce(output).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(output)
    render(<EditorRun />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show last run' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Show last run' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Saved review results')
  })

  it('offers a history retry instead of pretending there are no saved runs', async () => {
    vi.mocked(getWorkflowHistory).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ runs: [last] })
    render(<EditorRun />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your last run')
    fireEvent.click(screen.getByRole('button', { name: 'Retry last run' }))
    expect(await screen.findByRole('button', { name: 'Show last run' })).toBeVisible()
  })

  it('does not offer a nonexistent run', async () => {
    vi.mocked(getWorkflowHistory).mockResolvedValue({ runs: [] })
    const { result } = renderHook(() => useLastWorkflowRun('empty'))
    await act(async () => {})
    expect(result.current.lastRun).toBeNull()
    expect(result.current.error).toBeNull()
    expect(getWorkflowStatus).not.toHaveBeenCalled()
  })

  it('ignores a late history response when the editor switches workflows', async () => {
    let resolve!: (value: { runs: RunHistoryEntry[] }) => void
    vi.mocked(getWorkflowHistory).mockReturnValueOnce(new Promise(r => { resolve = r }))
      .mockResolvedValueOnce({ runs: [{ ...last, session_id: 'new-run' }] })
    const { result, rerender } = renderHook(({ id }) => useLastWorkflowRun(id, 'share-token'), { initialProps: { id: 'old' } })
    rerender({ id: 'new' })
    await waitFor(() => expect(result.current.lastRun?.session_id).toBe('new-run'))
    await act(async () => resolve({ runs: [last] }))
    expect(result.current.lastRun?.session_id).toBe('new-run')
    expect(getWorkflowStatus).toHaveBeenCalledWith('new-run', 'share-token')
    expect(getWorkflowStatus).not.toHaveBeenCalledWith('persisted-run', 'share-token')
  })
})
