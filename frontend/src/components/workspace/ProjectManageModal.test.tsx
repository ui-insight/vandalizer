import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProjectManageModal } from './ProjectManageModal'
import type { ProjectOverview } from '../../types/project'

const mocks = vi.hoisted(() => ({ project: undefined as ProjectOverview | undefined, update: vi.fn(), refresh: vi.fn(), members: vi.fn(), close: vi.fn(), mode: vi.fn() }))
vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: ReactNode }) => <>{children}</> }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../hooks/useProjects', () => ({ useProject: () => ({ project: mocks.project, update: mocks.update, loading: false, error: mocks.project ? null : new Error('Unavailable'), refresh: mocks.refresh }) }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ activeProjectUuid: 'a', refreshActiveProject: vi.fn(), deactivateProject: vi.fn(), setWorkspaceMode: mocks.mode }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'user-a' } }) }))
vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: null }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../projects/ProjectPinsSection', () => ({ ProjectPinsSection: () => <div>Pinned tools</div> }))
vi.mock('../../api/projects', () => ({ listProjectMembers: mocks.members }))
const setup = () => render(<QueryClientProvider client={new QueryClient()}><ProjectManageModal open onClose={mocks.close} /></QueryClientProvider>)
beforeEach(() => {
  vi.clearAllMocks(); mocks.members.mockResolvedValue([])
  mocks.project = { uuid: 'a', title: 'Grant A', description: 'A description', role: 'owner', owner_user_id: 'user-a', state: 'draft', team_id: null, capabilities: { files: { count: 0, folders: 0 }, knowledge: { ready: false, documents: 0 }, workflows: { count: 0 }, extractions: { count: 0 }, automations: { count: 0 }, external_kbs: { count: 0 }, members: { count: 1 } } } as ProjectOverview
})
describe('Project detail recovery', () => {
  it('keeps a failed title draft and does not submit twice while saving', async () => {
    mocks.update.mockRejectedValueOnce(new Error('Save unavailable'))
    setup(); fireEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    const title = screen.getByRole('textbox', { name: 'Project title' })
    fireEvent.change(title, { target: { value: 'Updated grant' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save title' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your edit is preserved')
    expect(title).toHaveValue('Updated grant')
    let finish!: () => void
    mocks.update.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve }))
    fireEvent.click(screen.getByRole('button', { name: 'Save title' }))
    fireEvent.keyDown(title, { key: 'Enter' })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(mocks.update).toHaveBeenCalledTimes(2)
    expect(mocks.close).not.toHaveBeenCalled()
    finish()
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Project title' })).not.toBeInTheDocument())
  })
  it('Escape cancels an edit before it closes the panel', () => {
    setup(); fireEvent.click(screen.getByRole('button', { name: 'Rename project' }))
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Project title' }), { key: 'Escape' })
    expect(mocks.close).not.toHaveBeenCalled()
    expect(mocks.update).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox', { name: 'Project title' })).not.toBeInTheDocument()
  })
  it('retains failed descriptions and selected status for retry', async () => {
    mocks.update.mockRejectedValue(new Error('offline'))
    setup(); fireEvent.click(screen.getByRole('button', { name: 'Edit description' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Project description' }), { target: { value: 'Keep this edit' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save description' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('textbox', { name: 'Project description' })).toHaveValue('Keep this edit')
    fireEvent.change(screen.getByRole('combobox', { name: 'Project status' }), { target: { value: 'active' } })
    await screen.findByRole('button', { name: 'Retry status' })
    expect(screen.getByRole('combobox', { name: 'Project status' })).toHaveValue('active')
    mocks.update.mockResolvedValue({})
    fireEvent.click(screen.getByRole('button', { name: 'Retry status' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Retry status' })).not.toBeInTheDocument())
    expect(mocks.update).toHaveBeenLastCalledWith({ state: 'active' })
  })
  it('offers retry for project and member loading failures', async () => {
    mocks.members.mockRejectedValueOnce(new Error('offline'))
    const rendered = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Retry members' }))
    await waitFor(() => expect(mocks.members).toHaveBeenCalledTimes(2))
    rendered.unmount(); mocks.project = undefined; setup()
    fireEvent.click(screen.getByRole('button', { name: 'Retry project' }))
    expect(mocks.refresh).toHaveBeenCalledOnce()
  })
  it('gives viewers a useful next step without edit or sharing controls', () => {
    mocks.project = { ...mocks.project!, role: 'viewer', owner_user_id: 'someone-else' }
    setup()
    expect(screen.getByText(/You have read-only access/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rename project' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add project files' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite link' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open project chat' }))
    expect(mocks.mode).toHaveBeenCalledWith('chat')
    expect(mocks.members).not.toHaveBeenCalled()
  })
})
