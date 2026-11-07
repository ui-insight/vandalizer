import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { WorkflowStatus } from '../../types/workflow'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflowShareToken: null }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ refresh: vi.fn() }) }))

const { WorkflowOutputCard } = await import('./WorkflowEditorPanel')

const completed = (workflow_version: number | null): WorkflowStatus => ({
  status: 'completed', num_steps_completed: 3, num_steps_total: 3, current_step_name: null,
  current_step_detail: null, current_step_preview: null, steps_output: {}, output_step_names: [],
  approval_request_id: null, final_output: { output: 'Three-line subaward summary' }, workflow_version,
})

const card = (status: WorkflowStatus, currentVersion: number) => render(
  <WorkflowOutputCard status={status} sessionId="run-1" workflowName="QA Subaward Quick Check" currentVersion={currentVersion}
    running={false} runElapsed={0} showDownloadPopup={false} setShowDownloadPopup={vi.fn()} />,
)

describe('WorkflowOutputCard after the workflow changed version', () => {
  it('labels a result from a replaced version and offers no download or save', () => {
    card(completed(2), 3)
    expect(screen.getByText('Result from version 2')).toBeTruthy()
    expect(screen.getByRole('note').textContent).toContain('before the workflow changed to version 3')
    expect(screen.queryByRole('button', { name: /Download/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Save to folder/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Save as page/ })).toBeNull()
    expect(screen.getByText('Three-line subaward summary')).toBeTruthy()
  })

  it('treats a result of the current version, or an unversioned older run, as the output', () => {
    for (const version of [3, null]) {
      const { unmount } = card(completed(version), 3)
      expect(screen.getByText('Output')).toBeTruthy()
      expect(screen.queryByRole('note')).toBeNull()
      expect(screen.getByRole('button', { name: /Save to folder/ })).toBeTruthy()
      unmount()
    }
  })
})
