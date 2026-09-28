import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { AutomationRunNowPanel, describeRunNowSource, describeRunNowResult } from './AutomationRunNowPanel'
import { runAutomationNow, getAutomationRun } from '../../api/automations'
import { searchDocuments } from '../../api/documents'
import type { Automation } from '../../types/automation'

vi.mock('../../api/automations', () => ({
  runAutomationNow: vi.fn(),
  getAutomationRun: vi.fn(),
}))
vi.mock('../../api/documents', () => ({
  searchDocuments: vi.fn().mockResolvedValue({ items: [{ uuid: 'd9', title: 'Pick me.pdf', extension: 'pdf' }] }),
}))

function auto(overrides: Partial<Automation> = {}): Automation {
  return {
    id: 'auto-1', name: 'Nightly', description: null, enabled: false,
    trigger_type: 'folder_watch', trigger_config: { folder_id: 'F1' },
    action_type: 'workflow', action_id: 'wf-1', action_name: 'Review', user_id: 'u', team_id: null,
    shared_with_team: false, output_config: {}, created_at: '', updated_at: '', can_manage: true,
    ...overrides,
  }
}

describe('describeRunNowSource / describeRunNowResult', () => {
  it('explains where the documents come from per trigger', () => {
    expect(describeRunNowSource(auto())).toMatch(/currently in the watched folder/)
    expect(describeRunNowSource(auto({ trigger_config: {} }))).toMatch(/Choose a watched folder/)
    expect(describeRunNowSource(auto({ trigger_type: 'schedule' }))).toMatch(/configured with/)
    expect(describeRunNowSource(auto({ trigger_type: 'api' }))).toMatch(/choose the documents/)
  })

  it('reports the outcome', () => {
    const base = { trigger_event_id: 'e', action_type: 'workflow', created_at: null, started_at: null, completed_at: null, output: null, error: null }
    expect(describeRunNowResult({ ...base, status: 'completed' })).toMatchObject({ tone: 'ok' })
    expect(describeRunNowResult({ ...base, status: 'failed', error: 'boom' })).toEqual({ tone: 'bad', text: 'Run failed: boom.' })
    expect(describeRunNowResult({ ...base, status: 'skipped', error: 'no docs' })).toMatchObject({ tone: 'warn' })
  })
})

describe('AutomationRunNowPanel', () => {
  beforeEach(() => {
    vi.mocked(runAutomationNow).mockReset()
    vi.mocked(getAutomationRun).mockReset()
    vi.mocked(searchDocuments).mockReset().mockResolvedValue({ items: [{ uuid: 'd9', title: 'Pick me.pdf' }], total: 1 } as Awaited<ReturnType<typeof searchDocuments>>)
  })

  it('warns that it is a real run and runs a folder-watch automation with one click, then polls to completion', async () => {
    vi.mocked(runAutomationNow).mockResolvedValue({
      status: 'queued', trigger_event_id: 'evt-1', action_type: 'workflow',
      documents: [{ uuid: 'd1', title: 'award.pdf' }], document_source: 'folder', documents_matched: 1,
    })
    vi.mocked(getAutomationRun)
      .mockResolvedValueOnce({ trigger_event_id: 'evt-1', status: 'running', action_type: 'workflow', created_at: null, started_at: null, completed_at: null, output: null, error: null })
      .mockResolvedValue({ trigger_event_id: 'evt-1', status: 'completed', action_type: 'workflow', created_at: null, started_at: null, completed_at: null, output: 'Done text', error: null })

    render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    expect(screen.getByRole('note')).toHaveTextContent(/real run, not a dry run/)
    expect(screen.getByRole('note')).toHaveTextContent(/does not switch it on/)

    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await waitFor(() => expect(runAutomationNow).toHaveBeenCalledWith('auto-1', []))
    await waitFor(() => expect(screen.getByText(/award\.pdf/)).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText(/Run completed/)).toBeInTheDocument(), { timeout: 8000 })
    expect(getAutomationRun).toHaveBeenCalledWith('auto-1', 'evt-1')
    expect(screen.getByText('Output')).toBeInTheDocument()
  }, 10000)

  it('requires chosen documents for an API automation and sends them', async () => {
    vi.mocked(runAutomationNow).mockResolvedValue({
      status: 'queued', trigger_event_id: 'evt-2', action_type: 'workflow',
      documents: [{ uuid: 'd9', title: 'Pick me.pdf' }], document_source: 'chosen', documents_matched: 1,
    })
    vi.mocked(getAutomationRun).mockResolvedValue({ trigger_event_id: 'evt-2', status: 'completed', action_type: 'workflow', created_at: null, started_at: null, completed_at: null, output: null, error: null })

    render(<AutomationRunNowPanel automation={auto({ trigger_type: 'api', trigger_config: {} })} canManage onClose={vi.fn()} />)
    const run = screen.getByRole('button', { name: 'Run now' })
    expect(run).toBeDisabled()

    const search = screen.getByLabelText('Search documents to run with')
    fireEvent.focus(search)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose Pick me.pdf' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Choose Pick me.pdf' }))
    expect(run).not.toBeDisabled()

    fireEvent.click(run)
    await waitFor(() => expect(runAutomationNow).toHaveBeenCalledWith('auto-1', ['d9']))
  })

  it('shows the server reason when the run cannot start', async () => {
    vi.mocked(runAutomationNow).mockRejectedValue(new Error('The watched folder has no documents that pass this automation’s file filters.'))
    render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/no documents that pass/))
  })

  it('is disabled without manage rights or an action', () => {
    render(<AutomationRunNowPanel automation={auto()} canManage={false} onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Run now' })).toBeDisabled()
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}
const accepted = { status: 'queued', trigger_event_id: 'evt-recovery', action_type: 'workflow', documents: [{ uuid: 'd9', title: 'Pick me.pdf' }], document_source: 'chosen' as const, documents_matched: 1 }
const completed = { trigger_event_id: 'evt-recovery', status: 'completed', action_type: 'workflow', created_at: null, started_at: null, completed_at: null, output: 'Retained output', error: null }

describe('manual run recovery and request isolation', () => {
  beforeEach(() => { vi.mocked(runAutomationNow).mockReset(); vi.mocked(getAutomationRun).mockReset(); vi.mocked(searchDocuments).mockReset() })

  it('retries a failed document search without losing the query and exposes keyboard buttons', async () => {
    vi.mocked(searchDocuments).mockRejectedValueOnce(new Error('Search unavailable')).mockResolvedValue({ items: [{ uuid: 'd9', title: 'Pick me.pdf' }] } as Awaited<ReturnType<typeof searchDocuments>>)
    render(<AutomationRunNowPanel automation={auto({ trigger_type: 'api' })} canManage onClose={vi.fn()} />)
    const input = screen.getByLabelText('Search documents to run with')
    fireEvent.change(input, { target: { value: 'Pick' } }); fireEvent.focus(input)
    expect(await screen.findByRole('alert')).toHaveTextContent('Search unavailable')
    expect(screen.queryByText(/No documents found/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry document search' }))
    const choice = await screen.findByRole('button', { name: 'Choose Pick me.pdf' })
    expect(input).toHaveValue('Pick')
    expect(vi.mocked(searchDocuments).mock.calls).toEqual([['Pick', 20], ['Pick', 20]])
    fireEvent.click(choice)
    expect(screen.getByRole('button', { name: 'Remove Pick me.pdf' })).toBeInTheDocument()
    expect(input).toHaveFocus()
  })

  it('ignores a slow earlier search after a new query resolves', async () => {
    const old = deferred<Awaited<ReturnType<typeof searchDocuments>>>()
    vi.mocked(searchDocuments).mockReturnValueOnce(old.promise).mockResolvedValue({ items: [{ uuid: 'new', title: 'Current.pdf' }] } as Awaited<ReturnType<typeof searchDocuments>>)
    render(<AutomationRunNowPanel automation={auto({ trigger_type: 'api' })} canManage onClose={vi.fn()} />)
    const input = screen.getByLabelText('Search documents to run with'); fireEvent.focus(input)
    await waitFor(() => expect(searchDocuments).toHaveBeenCalledTimes(1))
    fireEvent.change(input, { target: { value: 'current' } })
    await screen.findByRole('button', { name: 'Choose Current.pdf' })
    await act(async () => old.resolve({ items: [{ uuid: 'old', title: 'Old.pdf' }] } as Awaited<ReturnType<typeof searchDocuments>>))
    expect(screen.queryByRole('button', { name: 'Choose Old.pdf' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose Current.pdf' })).toBeInTheDocument()
  })

  it('blocks duplicate starts and retries only the status of an accepted run', async () => {
    const start = deferred<typeof accepted>()
    vi.mocked(runAutomationNow).mockReturnValue(start.promise)
    vi.mocked(getAutomationRun).mockRejectedValueOnce(new Error('Status service unavailable')).mockResolvedValue(completed)
    render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Run now' }); fireEvent.click(button); fireEvent.click(button)
    expect(runAutomationNow).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Starting…' })).toBeDisabled()
    await act(async () => start.resolve(accepted))
    expect(await screen.findByRole('alert')).toHaveTextContent('Run accepted')
    expect(screen.getByRole('button', { name: 'Status unavailable' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry status check' }))
    await screen.findByText(/Run completed/)
    expect(runAutomationNow).toHaveBeenCalledTimes(1)
    expect(vi.mocked(getAutomationRun).mock.calls).toEqual([['auto-1', 'evt-recovery'], ['auto-1', 'evt-recovery']])
  })

  it('keeps completed output when a later run fails to start', async () => {
    vi.mocked(runAutomationNow).mockResolvedValueOnce(accepted).mockRejectedValueOnce(new Error('Start unavailable'))
    vi.mocked(getAutomationRun).mockResolvedValue(completed)
    render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Run now' })); await screen.findByText(/Run completed/)
    fireEvent.click(screen.getByRole('button', { name: 'Run again' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Start unavailable')
    expect(screen.getByText('Retained output')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run again' })).toBeEnabled()
  })

  it('ignores a late start after switching automations', async () => {
    const start = deferred<typeof accepted>(); vi.mocked(runAutomationNow).mockReturnValue(start.promise)
    const { rerender } = render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    rerender(<AutomationRunNowPanel automation={auto({ id: 'auto-2' })} canManage onClose={vi.fn()} />)
    await act(async () => start.resolve(accepted))
    expect(getAutomationRun).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeEnabled()
  })

  it('ignores a late status after switching automations', async () => {
    const status = deferred<typeof completed>(); vi.mocked(runAutomationNow).mockResolvedValue(accepted); vi.mocked(getAutomationRun).mockReturnValue(status.promise)
    const { rerender } = render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Run now' })); await waitFor(() => expect(getAutomationRun).toHaveBeenCalledTimes(1))
    rerender(<AutomationRunNowPanel automation={auto({ id: 'auto-2' })} canManage onClose={vi.fn()} />)
    await act(async () => status.resolve(completed))
    expect(screen.queryByText(/Run completed/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeEnabled()
  })
  it('does not overlap slow polls or poll again after a terminal result', async () => {
    vi.useFakeTimers()
    try {
      const status = deferred<typeof completed>()
      vi.mocked(runAutomationNow).mockResolvedValue(accepted)
      vi.mocked(getAutomationRun).mockReturnValueOnce(status.promise).mockResolvedValue(completed)
      render(<AutomationRunNowPanel automation={auto()} canManage onClose={vi.fn()} />)
      await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Run now' })) })
      expect(getAutomationRun).toHaveBeenCalledTimes(1)
      await act(async () => { await vi.advanceTimersByTimeAsync(12000) })
      expect(getAutomationRun).toHaveBeenCalledTimes(1)
      await act(async () => status.resolve({ ...completed, status: 'running' }))
      await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
      expect(getAutomationRun).toHaveBeenCalledTimes(2)
      expect(screen.getByText(/Run completed/)).toBeInTheDocument()
      await act(async () => { await vi.advanceTimersByTimeAsync(12000) })
      expect(getAutomationRun).toHaveBeenCalledTimes(2)
    } finally { vi.useRealTimers() }
  })

  it('preserves chosen documents on start failure and locks them during an accepted run', async () => {
    vi.mocked(searchDocuments).mockResolvedValue({ items: [{ uuid: 'd9', title: 'Pick me.pdf' }] } as Awaited<ReturnType<typeof searchDocuments>>)
    vi.mocked(runAutomationNow).mockRejectedValueOnce(new Error('Start unavailable')).mockResolvedValueOnce(accepted)
    vi.mocked(getAutomationRun).mockRejectedValue(new Error('Status unavailable'))
    render(<AutomationRunNowPanel automation={auto({ trigger_type: 'api' })} canManage onClose={vi.fn()} />)
    const input = screen.getByLabelText('Search documents to run with'); fireEvent.focus(input)
    fireEvent.click(await screen.findByRole('button', { name: 'Choose Pick me.pdf' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Start unavailable')
    expect(screen.getByRole('button', { name: 'Remove Pick me.pdf' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    await screen.findByRole('button', { name: 'Retry status check' })
    expect(input).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Remove Pick me.pdf' })).toBeDisabled()
    expect(vi.mocked(runAutomationNow).mock.calls).toEqual([['auto-1', ['d9']], ['auto-1', ['d9']]])
  })

})
