import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AutomationRunNowPanel, describeRunNowSource, describeRunNowResult } from './AutomationRunNowPanel'
import { runAutomationNow, getAutomationRun } from '../../api/automations'
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
    await waitFor(() => expect(screen.getByRole('option', { name: /Pick me/ })).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByRole('option', { name: /Pick me/ }))
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
