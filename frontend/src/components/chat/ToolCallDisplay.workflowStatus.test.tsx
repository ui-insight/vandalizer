import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// get_workflow_status waits up to a minute for a run to finish, so its
// in-progress line says why it is taking a while.
describe('workflow status check in progress', () => {
  it('says it is waiting for the run to finish', () => {
    render(<ToolStatusLine call={{ tool_name: 'get_workflow_status', tool_call_id: 's1', args: { session_id: 'run-1' } }} isActive />)
    expect(screen.getByText(/until it finishes \(up to a minute\)/)).toBeInTheDocument()
  })

  it('adds nothing for a quick check', () => {
    render(<ToolStatusLine call={{ tool_name: 'get_workflow_status', tool_call_id: 's2', args: { session_id: 'run-1', wait: false } }} isActive />)
    expect(screen.queryByText(/until it finishes/)).not.toBeInTheDocument()
  })
})
