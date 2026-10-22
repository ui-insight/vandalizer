import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { RunHistoryTab, buildHistoryCSV, type HistoryRun } from './RunHistoryTab'
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

  it('underlines a traced statement of a run opened from History, as the run view does', async () => {
    const output = '**Recipient:** Southern Utah University. Costs are reasonable.'
    mockGetWorkflowStatus.mockResolvedValue({
      status: 'completed',
      num_steps_completed: 2,
      num_steps_total: 2,
      current_step_name: null,
      current_step_detail: null,
      current_step_preview: null,
      final_output: { output, data: [] },
      steps_output: {},
      output_step_names: [],
      approval_request_id: null,
      sourcing: {
        status: 'done',
        sources: [{
          kind: 'document', document_uuid: 'noa', document_title: 'NoA.pdf', page: 4,
          quote: 'Recipient: Southern Utah University', excerpt: 'Recipient: Southern Utah University',
          quote_start: 0, quote_end: 35,
        }],
        targets: { final: { format: 'text', statements: [{ s: 15, e: 40, src: 0 }, { s: 41, e: 62 }], summary: { statements: 2, traced: 1 } } },
      },
    })

    const { container } = renderTab([makeRun()])
    fireEvent.click(await screen.findByRole('button', { expanded: false }))

    await waitFor(() => expect(screen.getByText('1 of 2 statements traced to a source')).toBeTruthy())
    const underline = container.querySelector('.src-u') as HTMLElement
    expect(underline.textContent).toBe('Southern Utah University.')
    fireEvent.click(underline)
    expect(screen.getByRole('dialog', { name: 'Source: NoA.pdf · p. 4' })).toBeTruthy()
  })

  it('keeps an opened run open when the editor re-renders with a new fetcher', async () => {
    mockGetWorkflowStatus.mockResolvedValue({ final_output: { output: 'Summary of the **grant proposal**' } } as never)
    const fetchHistory = vi.fn(() => Promise.resolve({ runs: [makeRun()] }))
    const { rerender } = render(
      <RunHistoryTab fetchHistory={() => fetchHistory()} historyKey="wf-1" type="workflow" />,
    )
    fireEvent.click(await screen.findByRole('button', { expanded: false }))
    await waitFor(() => expect(screen.getByText(/Summary of the/)).toBeTruthy())

    // The editor passes a fresh closure on every render (a run poll, say).
    rerender(<RunHistoryTab fetchHistory={() => fetchHistory()} historyKey="wf-1" type="workflow" />)
    rerender(<RunHistoryTab fetchHistory={() => fetchHistory()} historyKey="wf-1" type="workflow" />)
    expect(screen.getByText(/Summary of the/)).toBeTruthy()
    expect(fetchHistory).toHaveBeenCalledTimes(1)

    rerender(<RunHistoryTab fetchHistory={() => fetchHistory()} historyKey="wf-2" type="workflow" />)
    await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(2))
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
    expect(screen.getByText('Markdown').closest('a')?.getAttribute('href'))
      .toBe('/api/workflows/download?session_id=sess-abc&format=markdown')
    expect(vi.mocked(downloadResults)).toHaveBeenCalledWith('sess-abc', 'json', { parseStructured: false })
  })

  it('offers retry when the persisted result cannot be read', async () => {
    mockGetWorkflowStatus.mockRejectedValue(new Error('Not found'))

    renderTab([makeRun()])
    fireEvent.click(await screen.findByRole('button', { expanded: false }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Not found')
      expect(screen.getByRole('button', { name: 'Retry run output' })).toBeTruthy()
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


it('retries a failed history read instead of claiming there are no runs', async () => {
  const fetchHistory = vi.fn().mockRejectedValueOnce(new Error('History unavailable')).mockResolvedValueOnce({ runs: [makeRun()] })
  render(<RunHistoryTab fetchHistory={fetchHistory} type="workflow" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('History unavailable')
  expect(screen.queryByText(/No runs yet/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry run history' }))
  expect(await screen.findByText('completed')).toBeTruthy()
  expect(fetchHistory).toHaveBeenCalledTimes(2)
})

// Support ticket: History showed status, time, duration and tokens but not the
// model, and a workflow with per-step overrides gave no way to see which step
// used which model.
describe('models in run history', () => {
  it('names the model on the row', async () => {
    renderTab([makeRun({ models: ['gpt-oss-120b'] })], 'extraction')
    expect(await screen.findByText('gpt-oss-120b')).toBeTruthy()
  })

  it('shows which step used which model when they differ', async () => {
    mockGetWorkflowStatus.mockResolvedValue({ final_output: { output: 'done' } } as never)
    renderTab([makeRun({
      models: ['gpt-oss-120b', 'glm-5.3-flash'],
      step_models: [
        { index: 0, name: 'Extract dates', models: ['gpt-oss-120b'] },
        { index: 1, name: 'Summarize', models: ['glm-5.3-flash'] },
      ],
    })])
    fireEvent.click(await screen.findByText('gpt-oss-120b, glm-5.3-flash'))
    const table = await screen.findByRole('table', { name: 'Models by step' })
    expect(table.textContent).toContain('Extract datesgpt-oss-120b')
    expect(table.textContent).toContain('Summarizeglm-5.3-flash')
  })

  it('lets a failed run be expanded to see its step models', async () => {
    renderTab([makeRun({
      status: 'failed', session_id: undefined, error: 'Step failed',
      models: ['a', 'b'], step_models: [{ index: 0, name: 'One', models: ['a'] }, { index: 1, name: 'Two', models: ['b'] }],
    })])
    fireEvent.click(await screen.findByText('a, b'))
    expect(await screen.findByRole('table', { name: 'Models by step' })).toBeTruthy()
  })

  it('omits the step table when one model ran throughout', async () => {
    mockGetWorkflowStatus.mockResolvedValue({ final_output: { output: 'done' } } as never)
    renderTab([makeRun({ models: ['a'], step_models: [{ index: 0, name: 'One', models: ['a'] }] })])
    fireEvent.click(await screen.findByText('a'))
    await waitFor(() => expect(mockGetWorkflowStatus).toHaveBeenCalled())
    expect(screen.queryByRole('table', { name: 'Models by step' })).toBeNull()
  })

  it('exports models and per-step models to CSV', () => {
    const csv = buildHistoryCSV([
      makeRun({
        started_at: '2026-10-01T10:00:00Z', finished_at: '2026-10-01T10:00:04Z',
        models: ['gpt-oss-120b', 'glm-5.3-flash'],
        step_models: [{ index: 0, name: 'Extract', models: ['gpt-oss-120b'] }, { index: 1, name: null, models: ['glm-5.3-flash'] }],
      }),
      makeRun({ status: 'failed', error: 'Model said "no"' }),
    ], 'workflow')
    const [header, first, second] = csv.trim().split('\n')
    expect(header).toBe('"Started","Finished","Status","Duration (ms)","Input tokens","Output tokens","Documents","Models","Models by step","Error"')
    expect(first).toBe('"2026-10-01T10:00:00Z","2026-10-01T10:00:04Z","completed","4200","100","50","1","gpt-oss-120b; glm-5.3-flash","Extract: gpt-oss-120b; Step 2: glm-5.3-flash",""')
    expect(second.endsWith('"","","Model said ""no"""')).toBe(true)
  })
})
