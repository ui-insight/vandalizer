import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { WorkflowProgress, unwrapWorkflowOutput } from './ToolCallDisplay'
import { getWorkflowStatus } from '../../api/workflows'
import type { WorkflowStatus } from '../../types/workflow'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflow: vi.fn() }) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../api/workflows', () => ({ getWorkflowStatus: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => ({ refresh: vi.fn() }) }))

// What a Prompt → Approval run stored as its final output before the resume
// fix: the review's {"value": …} wrapper, serialized by the engine.
const WRAPPED = JSON.stringify({ value: '## Document Summary\n\nThis is an NIH R01 (July 2024 – June 2029).' }, null, 2)

describe('workflow run card output', () => {
  it('shows the text inside an approval-gate wrapper, not the JSON', async () => {
    const completed: WorkflowStatus = {
      status: 'completed', num_steps_completed: 2, num_steps_total: 2, current_step_name: null,
      current_step_detail: null, current_step_preview: null, final_output: { output: WRAPPED },
      steps_output: {}, output_step_names: [], approval_request_id: null,
    }
    vi.mocked(getWorkflowStatus).mockResolvedValue(completed)
    render(<WorkflowProgress sessionId="session-1" />)
    expect(await screen.findByRole('heading', { name: 'Document Summary' })).toBeInTheDocument()
    expect(screen.getByText(/July 2024 – June 2029/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('"value"')
  })

  it('leaves other JSON output alone', () => {
    const structured = JSON.stringify({ value: 'x', total: 3 })
    expect(unwrapWorkflowOutput({ output: structured })).toBe(structured)
    expect(unwrapWorkflowOutput(JSON.stringify({ value: 42 }))).toBe('{"value":42}')
    expect(unwrapWorkflowOutput('{ not json')).toBe('{ not json')
  })
})
