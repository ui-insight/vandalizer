import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AutomationRunHistory } from './AutomationRunHistory'
import { getAutomationHistory, getAutomationRun } from '../../api/automations'
import type { AutomationRunStatus } from '../../types/automation'
vi.mock('../../api/automations', () => ({ getAutomationHistory: vi.fn(), getAutomationRun: vi.fn() }))
const run = (id: string, status = 'completed'): AutomationRunStatus => ({ trigger_event_id: id, status, action_type: 'workflow', created_at: '2026-09-28T12:00:00Z', started_at: null, completed_at: null, output: null, error: null })
const cursor = { before: '2026-09-28T12:00:00Z', before_id: 'run-first' }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
beforeEach(() => { vi.mocked(getAutomationHistory).mockReset(); vi.mocked(getAutomationRun).mockReset() })
const props = { automationId: 'a', open: true, canRun: true, onPrepareRun: vi.fn() }
describe('automation run history', () => {
  it('retries a failed page at the same cursor while preserving previous runs', async () => {
    vi.mocked(getAutomationHistory).mockResolvedValueOnce({ items: [run('first')], next_cursor: cursor }).mockRejectedValueOnce(new Error('History unavailable')).mockResolvedValueOnce({ items: [run('older')], next_cursor: null })
    render(<AutomationRunHistory {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Load older runs' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Previously loaded runs are preserved')
    expect(screen.getByRole('button', { name: 'Open run first' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry history' }))
    await screen.findByRole('button', { name: 'Open run older' })
    expect(vi.mocked(getAutomationHistory).mock.calls).toEqual([['a', undefined], ['a', cursor], ['a', cursor]])
    expect(screen.queryByRole('button', { name: 'Load older runs' })).not.toBeInTheDocument()
  })
  it('distinguishes failed loading from an empty history', async () => {
    vi.mocked(getAutomationHistory).mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ items: [], next_cursor: null })
    render(<AutomationRunHistory {...props} />)
    await screen.findByRole('alert'); expect(screen.queryByText(/No recorded runs/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry history' }))
    expect(await screen.findByText(/No recorded runs yet/)).toBeInTheDocument()
  })
  it('ignores late history from a different automation', async () => {
    const old = deferred<Awaited<ReturnType<typeof getAutomationHistory>>>()
    vi.mocked(getAutomationHistory).mockReturnValueOnce(old.promise).mockResolvedValueOnce({ items: [run('new')], next_cursor: null })
    const { rerender } = render(<AutomationRunHistory {...props} />)
    rerender(<AutomationRunHistory {...props} automationId="b" />)
    await screen.findByRole('button', { name: 'Open run new' })
    await act(async () => old.resolve({ items: [run('old')], next_cursor: null }))
    expect(screen.queryByRole('button', { name: 'Open run old' })).not.toBeInTheDocument()
  })
  it('retries details for the selected persisted run and restores focus on close', async () => {
    vi.mocked(getAutomationHistory).mockResolvedValue({ items: [run('failed', 'failed')], next_cursor: null })
    vi.mocked(getAutomationRun).mockRejectedValueOnce(new Error('Status unavailable')).mockResolvedValueOnce({ ...run('failed', 'failed'), error: 'One source failed', output: 'Completed portion' })
    render(<AutomationRunHistory {...props} />)
    const trigger = await screen.findByRole('button', { name: 'Open run failed' }); fireEvent.click(trigger)
    expect(screen.getByRole('heading', { name: 'Run details' })).toHaveFocus()
    const detail = screen.getByRole('region', { name: 'Run details failed' })
    await within(detail).findByRole('button', { name: 'Retry run details' })
    fireEvent.click(within(detail).getByRole('button', { name: 'Retry run details' }))
    await within(detail).findByText('Completed portion')
    expect(within(detail).getByText('One source failed')).toBeInTheDocument()
    expect(vi.mocked(getAutomationRun).mock.calls).toEqual([['a', 'failed'], ['a', 'failed']])
    fireEvent.click(within(detail).getByRole('button', { name: 'Prepare another run' }))
    expect(props.onPrepareRun).toHaveBeenCalledOnce()
    fireEvent.click(within(detail).getByRole('button', { name: 'Close run details' }))
    expect(trigger).toHaveFocus()
  })
  it('opens history for readers without offering a new run', async () => {
    vi.mocked(getAutomationHistory).mockResolvedValue({ items: [run('done')], next_cursor: null }); vi.mocked(getAutomationRun).mockResolvedValue(run('done'))
    render(<AutomationRunHistory {...props} canRun={false} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open run done' }))
    await screen.findByText('No output was recorded for this run.')
    expect(screen.queryByRole('button', { name: 'Prepare another run' })).not.toBeInTheDocument()
  })
  it('ignores a detail response after a different row is selected', async () => {
    const old = deferred<AutomationRunStatus>()
    vi.mocked(getAutomationHistory).mockResolvedValue({ items: [run('a'), run('b')], next_cursor: null })
    vi.mocked(getAutomationRun).mockReturnValueOnce(old.promise).mockResolvedValueOnce({ ...run('b'), output: 'B output' })
    render(<AutomationRunHistory {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open run a' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open run b' }))
    await screen.findByText('B output'); await act(async () => old.resolve({ ...run('a'), output: 'A output' }))
    expect(screen.queryByText('A output')).not.toBeInTheDocument()
  })
  it('does not overlap polling and stops at completion', async () => {
    vi.useFakeTimers()
    try {
      const pending = deferred<AutomationRunStatus>()
      vi.mocked(getAutomationHistory).mockResolvedValue({ items: [run('live', 'running')], next_cursor: null })
      vi.mocked(getAutomationRun).mockReturnValueOnce(pending.promise).mockResolvedValueOnce({ ...run('live'), output: 'Finished' })
      await act(async () => { render(<AutomationRunHistory {...props} />) })
      fireEvent.click(screen.getByRole('button', { name: 'Open run live' }))
      await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
      expect(getAutomationRun).toHaveBeenCalledTimes(1)
      await act(async () => pending.resolve(run('live', 'running')))
      await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
      expect(screen.getByText('Finished')).toBeInTheDocument()
      await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
      expect(getAutomationRun).toHaveBeenCalledTimes(2)
    } finally { vi.useRealTimers() }
  })
  it('waits until history is opened before fetching', async () => {
    vi.mocked(getAutomationHistory).mockResolvedValue({ items: [], next_cursor: null })
    const { rerender } = render(<AutomationRunHistory {...props} open={false} />)
    expect(getAutomationHistory).not.toHaveBeenCalled()
    rerender(<AutomationRunHistory {...props} />)
    await waitFor(() => expect(getAutomationHistory).toHaveBeenCalledOnce())
  })
})
