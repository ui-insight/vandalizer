import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkflowProgress } from './ToolCallDisplay'
import { getWorkflowStatus } from '../../api/workflows'
import type { WorkflowStatus } from '../../types/workflow'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflow: vi.fn() }) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../api/workflows', () => ({ getWorkflowStatus: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => ({ refresh: vi.fn() }) }))

const status = (changes: Partial<WorkflowStatus>): WorkflowStatus => ({
  status: 'completed', num_steps_completed: 2, num_steps_total: 2, current_step_name: null,
  current_step_detail: null, current_step_preview: null, final_output: 'Done', steps_output: null,
  output_step_names: [], approval_request_id: null, ...changes,
})

beforeEach(() => { vi.clearAllMocks() })

describe('a chat-started workflow run names its model (ticket)', () => {
  it('shows the model the steps ran on', async () => {
    vi.mocked(getWorkflowStatus).mockResolvedValue(status({ model: 'moonshotai/kimi-k3', models_used: ['moonshotai/kimi-k3'] }))
    render(<WorkflowProgress sessionId="s-1" workflowId="wf-1" />)
    expect(await screen.findByText('Model: moonshotai/kimi-k3')).toBeInTheDocument()
  })

  it('lists both models when a step set its own', async () => {
    vi.mocked(getWorkflowStatus).mockResolvedValue(status({ model: 'moonshotai/kimi-k3', models_used: ['moonshotai/kimi-k3', 'VandalAI'] }))
    render(<WorkflowProgress sessionId="s-2" />)
    expect(await screen.findByText('Models: moonshotai/kimi-k3, VandalAI')).toBeInTheDocument()
  })
})
