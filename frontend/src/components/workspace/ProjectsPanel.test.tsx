import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ProjectsPanel } from './ProjectsPanel'
import type { Project } from '../../types/project'

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), create: vi.fn(), duplicate: vi.fn(), refresh: vi.fn(), projects: [] as Project[], error: null as Error | null }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../hooks/useProjects', () => ({ useProjects: () => ({ ...mocks, loading: false }) }))

beforeEach(() => { vi.clearAllMocks(); mocks.error = null; mocks.projects = [] })
describe('Projects recovery', () => {
  it('preserves failed creation and prevents duplicate submissions while pending', async () => {
    mocks.create.mockRejectedValueOnce(new Error('Create unavailable'))
    render(<ProjectsPanel />)
    const input = screen.getByRole('textbox', { name: 'New project name' })
    fireEvent.change(input, { target: { value: 'Grant review' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your name is preserved')
    expect(input).toHaveValue('Grant review')
    let finish!: (value: { uuid: string }) => void
    mocks.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }))
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(input).toBeDisabled()
    expect(mocks.create).toHaveBeenCalledTimes(2)
    finish({ uuid: 'created' })
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith(expect.objectContaining({ search: expect.objectContaining({ project: 'created' }) })))
  })
  it('does not reopen a project when creation finishes after leaving the list', async () => {
    let finish!: (value: { uuid: string }) => void
    mocks.create.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const view = render(<ProjectsPanel />)
    fireEvent.change(screen.getByRole('textbox', { name: 'New project name' }), { target: { value: 'Later project' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create project' }))
    view.unmount()
    finish({ uuid: 'later' })
    await waitFor(() => expect(mocks.create).toHaveBeenCalledOnce())
    expect(mocks.navigate).not.toHaveBeenCalled()
  })
  it('retries a list failure and does not claim there are no projects', () => {
    mocks.error = new Error('offline')
    render(<ProjectsPanel />)
    fireEvent.click(screen.getByRole('button', { name: 'Retry projects' }))
    expect(mocks.refresh).toHaveBeenCalledOnce()
    expect(screen.queryByText('Bring your work together')).not.toBeInTheDocument()
  })
  it('keeps projects beyond the initial page available through search and show more', () => {
    mocks.projects = Array.from({ length: 61 }, (_, i) => ({ uuid: `p-${i}`, title: `Project ${String(i).padStart(2, '0')}`, state: 'draft', description: '', updated_at: '2026-09-28' } as Project))
    render(<ProjectsPanel />)
    expect(screen.queryByText('Project 60')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show more projects (21 remaining)' }))
    expect(screen.getByText('Project 60')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search projects' }), { target: { value: '60' } })
    expect(screen.getByText('Project 60')).toBeInTheDocument()
    expect(screen.queryByText('Project 00')).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search projects' }), { target: { value: 'absent' } })
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getByText('Project 00')).toBeInTheDocument()
  })
})
