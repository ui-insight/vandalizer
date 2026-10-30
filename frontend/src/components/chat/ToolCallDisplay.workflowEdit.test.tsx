import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

const workspace = vi.hoisted(() => ({ openWorkflow: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => workspace }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// Chat edits a workflow in place (support ticket: an NSF→USDA change left two workflows).
const call = { tool_name: 'update_workflow', tool_call_id: 'edit-1', args: { workflow_id: 'wf-1', change_summary: 'Check USDA rules' } }
const result = (content: unknown, id = 'edit-1') => ({ tool_name: 'update_workflow', tool_call_id: id, content, quality: null })

describe('update_workflow in chat', () => {
  beforeEach(() => vi.clearAllMocks())

  it('summarizes the edit with its version and opens the same workflow', () => {
    render(<ToolStatusLine call={call} result={result({ workflow_id: 'wf-1', name: 'USDA Subaward Compliance Scan', version: 3 })} />)
    expect(screen.getByText('Updated "USDA Subaward Compliance Scan" · version 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open workflow' }))
    expect(workspace.openWorkflow).toHaveBeenCalledWith('wf-1')
  })

  it('tells an editor showing the workflow to reload, once per edit', () => {
    const heard = vi.fn()
    const listener = (event: Event) => heard((event as CustomEvent<string>).detail)
    window.addEventListener('vandalizer:workflow-edited', listener)
    const view = render(<ToolStatusLine call={call} result={result({ workflow_id: 'wf-1', name: 'Scan', version: 2 }, 'edit-2')} />)
    view.rerender(<ToolStatusLine call={call} result={result({ workflow_id: 'wf-1', name: 'Scan', version: 2 }, 'edit-2')} />)
    view.unmount()
    render(<ToolStatusLine call={call} result={result({ workflow_id: 'wf-1', name: 'Scan', version: 2 }, 'edit-2')} />)
    window.removeEventListener('vandalizer:workflow-edited', listener)
    expect(heard).toHaveBeenCalledExactlyOnceWith('wf-1')
  })

  it('announces nothing for a preview awaiting approval', () => {
    const heard = vi.fn()
    window.addEventListener('vandalizer:workflow-edited', heard)
    render(<ToolStatusLine call={call} result={result({ workflow_id: 'wf-1', needs_confirmation: true, preview: 'Update workflow' }, 'edit-3')} />)
    window.removeEventListener('vandalizer:workflow-edited', heard)
    expect(heard).not.toHaveBeenCalled()
  })
})
