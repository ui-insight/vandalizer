import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { RunHistoryTab, type HistoryRun } from './RunHistoryTab'
import { getWorkflowStatus, downloadResults } from '../../api/workflows'

vi.mock('../../api/workflows', () => ({
  getWorkflowStatus: vi.fn(),
  downloadResults: vi.fn((sessionId: string, fmt: string) => `/api/workflows/download?session_id=${sessionId}&format=${fmt}`),
}))

const mockGetWorkflowStatus = vi.mocked(getWorkflowStatus)

function makeRun(overrides: Partial<HistoryRun> = {}): HistoryRun {
  return {
    id: 'run-1',
    status: 'completed',
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    duration_ms: 4200,
    error: '',
    tokens_input: 100,
    tokens_output: 50,
    documents_touched: 1,
    steps_completed: 2,
    steps_total: 2,
    session_id: 'sess-abc',
    result_snapshot: {},
    ...overrides,
  }
}

function renderTab(runs: HistoryRun[], type: 'workflow' | 'extraction' = 'workflow') {
  return render(
    <RunHistoryTab fetchHistory={() => Promise.resolve({ runs })} type={type} />,
  )
}

beforeEach(() => {
  mockGetWorkflowStatus.mockReset()
})

describe('RunHistoryTab — workflow run output', () => {
  it('expands a completed workflow run and shows its fetched output', async () => {
    mockGetWorkflowStatus.mockResolvedValue({
      status: 'completed',
      num_steps_completed: 2,
      num_steps_total: 2,
      current_step_name: null,
      current_step_detail: null,
      current_step_preview: null,
      final_output: { output: 'Summary of the **grant proposal**', data: [] },
      steps_output: {},
      output_step_names: [],
      approval_request_id: null,
    })

    renderTab([makeRun()])
    const row = await screen.findByRole('button', { expanded: false })
    fireEvent.click(row)

    await waitFor(() => {
      expect(screen.getByText(/Summary of the/)).toBeTruthy()
    })
    expect(mockGetWorkflowStatus).toHaveBeenCalledWith('sess-abc')
  })

  it('offers download formats for the expanded run', async () => {
    mockGetWorkflowStatus.mockResolvedValue({
      status: 'completed',
      num_steps_completed: 1,
      num_steps_total: 1,
      current_step_name: null,
      current_step_detail: null,
      current_step_preview: null,
      final_output: { output: 'done', data: [] },
      steps_output: {},
      output_step_names: [],
      approval_request_id: null,
    })

    renderTab([makeRun()])
    fireEvent.click(await screen.findByRole('button', { expanded: false }))
    fireEvent.click(await screen.findByText('Download'))

    expect(screen.getByText('JSON').closest('a')?.getAttribute('href'))
      .toBe('/api/workflows/download?session_id=sess-abc&format=json')
    expect(screen.getByText('PDF')).toBeTruthy()
    expect(screen.getByText('Word (.docx)')).toBeTruthy()
    expect(vi.mocked(downloadResults)).toHaveBeenCalledWith('sess-abc', 'json', { parseStructured: false })
  })

  it('shows a fallback when the persisted result is gone', async () => {
    mockGetWorkflowStatus.mockRejectedValue(new Error('Not found'))

    renderTab([makeRun()])
    fireEvent.click(await screen.findByRole('button', { expanded: false }))

    await waitFor(() => {
      expect(screen.getByText('Output is no longer available for this run.')).toBeTruthy()
    })
  })

  it('does not make failed runs expandable', async () => {
    renderTab([makeRun({ status: 'failed', error: 'boom' })])
    await screen.findByText('boom')
    expect(screen.queryByRole('button', { expanded: false })).toBeNull()
    expect(mockGetWorkflowStatus).not.toHaveBeenCalled()
  })

  it('does not make runs without a session_id expandable', async () => {
    renderTab([makeRun({ session_id: undefined })])
    await screen.findByText('completed')
    expect(screen.queryByRole('button', { expanded: false })).toBeNull()
  })
})

describe('RunHistoryTab — extraction runs (unchanged behavior)', () => {
  it('renders extracted fields from the inline snapshot without fetching', async () => {
    renderTab(
      [makeRun({ result_snapshot: { normalized: { sponsor: 'NSF', amount: '50000' } } })],
      'extraction',
    )
    fireEvent.click(await screen.findByRole('button', { expanded: false }))

    expect(screen.getByText('sponsor')).toBeTruthy()
    expect(screen.getByText('NSF')).toBeTruthy()
    expect(screen.getByText('amount')).toBeTruthy()
    expect(mockGetWorkflowStatus).not.toHaveBeenCalled()
  })

  it('extraction runs without a snapshot stay non-expandable', async () => {
    renderTab([makeRun()], 'extraction')
    await screen.findByText('completed')
    expect(screen.queryByRole('button', { expanded: false })).toBeNull()
  })
})
