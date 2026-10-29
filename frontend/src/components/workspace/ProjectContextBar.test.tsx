import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectContextBar } from './ProjectContextBar'
import { ProjectWorkOverview } from '../projects/ProjectWorkOverview'

const workspace = vi.hoisted(() => ({
  activeProjectUuid: 'award', activeProjectTitle: 'Award', activeProjectRole: 'owner',
  workspaceMode: 'chat', railDocked: true, setWorkspaceMode: vi.fn(),
  deactivateProject: vi.fn(), focusChat: vi.fn(),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => workspace }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: undefined }) }))
vi.mock('../../hooks/useProjectPins', () => ({ useProjectPins: () => ({ pins: [] }) }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
  workspace.workspaceMode = 'chat'
  workspace.activeProjectRole = 'owner'
})

describe.each([
  ['project header', () => <ProjectContextBar />],
  ['project overview', () => <ProjectWorkOverview uuid="award" />],
] as const)('%s file navigation', (_name, component) => {
  it('opens Files from another mode and hides the redundant action when Files is selected', () => {
    const view = render(component())
    fireEvent.click(screen.getByRole('button', { name: 'Open files' }))
    expect(workspace.setWorkspaceMode).toHaveBeenCalledExactlyOnceWith('files')
    workspace.workspaceMode = 'files'
    view.rerender(component())
    expect(screen.queryByRole('button', { name: 'Open files' })).not.toBeInTheDocument()
    workspace.workspaceMode = 'knowledge'
    view.rerender(component())
    expect(screen.getByRole('button', { name: 'Open files' })).toBeInTheDocument()
  })

  it('preserves the read-only project controls', () => {
    workspace.activeProjectRole = 'viewer'
    render(component())
    expect(screen.queryByRole('button', { name: 'Open files' })).not.toBeInTheDocument()
  })
})
