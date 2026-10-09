import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToolCallDisplay, ToolStatusLine, WorkflowProgress } from './ToolCallDisplay'
import { getWorkflowStatus } from '../../api/workflows'
import type { WorkflowStatus } from '../../types/workflow'

const workspace = { openWorkflow: vi.fn() }
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => workspace }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../api/workflows', () => ({ getWorkflowStatus: vi.fn() }))
const courseRefresh = vi.hoisted(() => vi.fn())
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => ({ refresh: courseRefresh }) }))
const status = (changes: Partial<WorkflowStatus> = {}): WorkflowStatus => ({ status:'running', num_steps_completed:1, num_steps_total:3, current_step_name:'Review findings', current_step_detail:null, current_step_preview:null, final_output:null, steps_output:{Extract:'Preserved findings'}, output_step_names:[], approval_request_id:null, ...changes })
const call = {tool_name:'create_workflow', tool_call_id:'call-1',args:{name:'Review proposal'}}
const result = (content: unknown) => ({tool_name:'create_workflow',tool_call_id:'call-1',content,quality:null})
beforeEach(() => { vi.clearAllMocks() })

describe('tool states and recovery', () => {
  it.each([
    [{needs_confirmation:true},'Awaiting approval'], [{status:'queued'},'Queued'], [{status:'running'},'Running'],
    [{status:'failed', error_detail:'Review step failed'},'Failed'], [{status:'canceled',error:'Canceled by user'},'Canceled'],
    [{status:'completed'},'Completed'], [{status:'custom_status'},'Result received'],
  ])('identifies protocol state %j without inferring execution', (content,label) => {
    render(<ToolStatusLine call={call} result={result(content)} />)
    expect(screen.getByRole('status')).toHaveTextContent(`Building workflow · ${label}`)
  })
  it('keeps approval available after a blocked decision and prevents duplicate accepted decisions', () => {
    const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValue(true)
    render(<ToolStatusLine call={call} result={result({needs_confirmation:true,preview:'Create a workflow'})} onConfirm={confirm} />)
    fireEvent.click(screen.getByRole('button',{name:'Create workflow'}))
    expect(screen.getByRole('alert')).toHaveTextContent('could not be sent yet')
    fireEvent.click(screen.getByRole('button',{name:'Create workflow'}))
    expect(screen.queryByRole('button',{name:'Create workflow'})).not.toBeInTheDocument()
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('status')).toHaveTextContent('Approval requested')
    expect(screen.getByText('Check the Assistant’s next response for the outcome.')).toBeInTheDocument()
  })
  it('offers persisted approvals without segments and reports cancellation as a request', () => {
    const confirm=vi.fn()
    render(<ToolCallDisplay toolCalls={[call]} toolResults={[result({needs_confirmation:true,preview:'Create a workflow'})]} onConfirm={confirm} />)
    fireEvent.click(screen.getByRole('button',{name:'Cancel action'}))
    expect(confirm).toHaveBeenCalledWith('No, cancel that')
    expect(screen.getByRole('status')).toHaveTextContent('Cancellation requested')
  })
  it('shows the failed tool and protocol hint while requesting recovery without repeating completed changes', () => {
    const confirm=vi.fn()
    render(<ToolStatusLine call={call} result={result({error:'Permission changed',hint:'Choose an accessible project.'})} onConfirm={confirm} />)
    expect(screen.getByText('Choose an accessible project.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Review recovery options'}))
    expect(confirm.mock.calls[0][0]).toContain('Do not repeat completed changes without my approval.')
  })
})

describe('workflow run recovery', () => {
  it('retries only the same status read and exposes preserved output and the exact run', async () => {
    vi.mocked(getWorkflowStatus).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(status({status:'failed',error:'Missing source'}))
    render(<WorkflowProgress sessionId="session-1" workflowId="workflow-1" initialStatus="queued" />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Checking again does not start another run')
    fireEvent.click(screen.getByRole('button',{name:'Check workflow status'}))
    await screen.findByText('Missing source')
    expect(screen.getByRole('status')).toHaveTextContent('Workflow failed · 1/3 steps completed')
    expect(screen.getByText('Failed step:')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Completed step results'))
    expect(screen.getByLabelText('Completed workflow step results')).toHaveTextContent('Preserved findings')
    fireEvent.click(screen.getByRole('button',{name:'Open this workflow run'}))
    expect(workspace.openWorkflow).toHaveBeenCalledWith('workflow-1','session-1')
    expect(vi.mocked(getWorkflowStatus).mock.calls).toEqual([['session-1'],['session-1']])
  })
  it('keeps the last results when a later poll fails and resumes after an explicit check', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(getWorkflowStatus).mockResolvedValueOnce(status()).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(status({status:'completed',final_output:{output:{summary:'Complete result '+ 'long '.repeat(100)}}}))
      render(<WorkflowProgress sessionId="session-2" />)
      await act(async () => { await Promise.resolve() })
      await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
      expect(screen.getByRole('alert')).toHaveTextContent('Last known state: Workflow running')
      expect(screen.getByLabelText('Completed workflow step results')).toHaveTextContent('Preserved findings')
      await act(async () => { fireEvent.click(screen.getByRole('button',{name:'Check workflow status'})); await Promise.resolve() })
      expect(screen.getByRole('status')).toHaveTextContent('Workflow complete')
      expect(screen.getByLabelText('Workflow output')).toHaveTextContent('long '.repeat(100).trim())
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    } finally { vi.useRealTimers() }
  })
  it('labels a run waiting at an approval gate instead of showing the raw status', async () => {
    vi.mocked(getWorkflowStatus).mockResolvedValue(status({status:'pending_approval',num_steps_completed:1,num_steps_total:2,current_step_name:'Approval'}))
    render(<WorkflowProgress sessionId="session-4" />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Awaiting workflow approval · 1/2 steps completed'))
  })
  it('announces clipboard failure instead of claiming the result was copied', async () => {
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce(undefined)}})
    vi.mocked(getWorkflowStatus).mockResolvedValue(status({status:'completed',final_output:'Saved result'}))
    render(<WorkflowProgress sessionId="session-3" />)
    fireEvent.click(await screen.findByRole('button',{name:'Copy workflow output'}))
    await screen.findByText('Copy failed. Try again or select the result text.')
    fireEvent.click(screen.getByRole('button',{name:'Copy workflow output'}))
    await waitFor(()=>expect(screen.getByText('Copy workflow output: copied')).toBeInTheDocument())
  })
})

it('renders a historical approval as a nonactionable record even when a callback exists', () => {
  const confirm = vi.fn()
  render(<ToolStatusLine call={call} result={result({ needs_confirmation: true, preview: 'Create a workflow' })} onConfirm={confirm} approvalHistory={{ label: 'Workflow created', detail: 'Inspect the result below.' }} />)
  expect(screen.getByRole('region', { name: 'Earlier action decision' })).toHaveTextContent('Workflow created')
  expect(screen.queryByRole('button', { name: 'Create workflow' })).toBeNull()
  expect(screen.queryByText('Your approval is needed')).toBeNull()
  expect(confirm).not.toHaveBeenCalled()
})

it.each([
  ['get_certification_progress', { modules: { wrong: 'shape' } }],
  ['get_certification_lesson', { content: 'Incomplete teaching payload' }],
  ['check_certification_module', { passed: 'false', checks: {} }],
  ['complete_certification_module', { total_xp: 125, certified: 'false' }],
  ['submit_certification_assessment', { stored: false }],
])('does not render malformed %s as a successful course operation', (tool_name, content) => {
  const confirm = vi.fn()
  render(<ToolStatusLine call={{ tool_name, tool_call_id: 'cert-bad', args: {} }} result={{ tool_name, tool_call_id: 'cert-bad', content, quality: null }} onConfirm={confirm} />)
  expect(screen.getByRole('status')).toHaveTextContent('Result needs review')
  expect(screen.getByRole('alert')).toHaveTextContent('Saved work may already exist')
  expect(screen.queryByRole('button', { name: 'Complete the module' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Review recovery options' })).not.toBeInTheDocument()
  expect(confirm).not.toHaveBeenCalled()
})


it('keeps the tool summary consistent with an optional check that did not pass', () => {
  const tool_name = 'check_certification_module'
  render(<ToolStatusLine result={{ tool_name, tool_call_id: 'advisory', quality: null, content: { module_id: 'foundations', title: 'Foundations', passed: true, stars: 1, checks: [{ name: 'Required run', passed: true, detail: 'Saved' }, { name: 'Enrichment', passed: false, detail: 'Optional' }] } }} />)
  expect(screen.getByText('"Foundations" — module requirements met; review check details')).toBeInTheDocument()
  expect(screen.queryByText(/all checks passed/)).not.toBeInTheDocument()
})


it('checks saved progress after an uncertain write without asking the agent to repeat it', async () => {
  courseRefresh.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(undefined)
  const confirm = vi.fn(), tool_name = 'complete_certification_module'
  render(<ToolStatusLine result={{ tool_name, tool_call_id: 'uncertain', content: { total_xp: 100 }, quality: null }} onConfirm={confirm} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved course progress' }))
  await screen.findByText('Progress could not be refreshed. Keep your saved work and try this read again.')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved course progress' }))
  await screen.findByText('Current progress loaded. Open the learning panel to inspect your saved work.')
  expect(courseRefresh).toHaveBeenCalledTimes(2)
  expect(confirm).not.toHaveBeenCalled()
})

describe('document search with no exact match', () => {
  const search = { tool_name: 'search_documents', tool_call_id: 'call-s', args: { query: 'nih-ro1-neuroscience.pdf' } }
  const searched = (content: unknown) => ({ tool_name: 'search_documents', tool_call_id: 'call-s', content, quality: null })
  it('names the closest title instead of a bare not-found', () => {
    render(<ToolStatusLine call={search} result={searched({ documents: [], did_you_mean: [{ uuid: 'd1', title: 'nih-r01-neuroscience.pdf' }] })} />)
    expect(screen.getByText('No exact match · did you mean "nih-r01-neuroscience.pdf"?')).toBeInTheDocument()
  })
  it('still says nothing was found when nothing is close', () => {
    render(<ToolStatusLine call={search} result={searched({ documents: [], did_you_mean: [] })} />)
    expect(screen.getByText('No documents found')).toBeInTheDocument()
  })
})
