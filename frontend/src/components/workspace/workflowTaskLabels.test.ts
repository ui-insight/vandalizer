import { describe, expect, it, vi } from 'vitest'
import { workflowTaskLabel } from './workflowTaskLabels'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openWorkflowShareToken: null }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ refresh: vi.fn() }) }))

const { TASK_TYPES } = await import('./WorkflowEditorPanel')

// Support ticket: the Add a task list showed "CreateProject", "InboxDeadlines"
// and "AwardSnapshotPage": new task types with no entry in the label map.
describe('Add a task labels', () => {
  it('names the Workspace tasks in plain words', () => {
    expect(workflowTaskLabel('CreateProject')).toBe('Create project')
    expect(workflowTaskLabel('InboxDeadlines')).toBe('Add deadlines to RA inbox')
    expect(workflowTaskLabel('AwardSnapshotPage')).toBe('Award snapshot page')
  })

  it('gives every task in the list a readable label, not its code name', () => {
    // A code name: two capitals in a row or a lower-to-upper join ("APINode", "CreateProject").
    const unlabeled = TASK_TYPES.filter(task => /[a-z][A-Z]|^[A-Z]{2}/.test(workflowTaskLabel(task.name)))
    expect(unlabeled.map(task => task.name)).toEqual([])
  })
})
