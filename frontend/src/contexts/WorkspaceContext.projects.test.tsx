import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'
import type { ProjectOverview } from '../types/project'

const mocks = vi.hoisted(() => ({ search: {} as Record<string, string>, navigate: vi.fn(), getProject: vi.fn(), toast: vi.fn(), team: { uuid: 'team-1' }, teamsLoading: false }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mocks.navigate, useSearch: () => mocks.search }))
vi.mock('../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: mocks.team, loading: mocks.teamsLoading }) }))
vi.mock('./ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))
vi.mock('../api/projects', () => ({ getProject: mocks.getProject }))
const project = (uuid: string): ProjectOverview => ({ uuid, title: `Project ${uuid}`, root_folder_uuid: `root-${uuid}`, team_id: 'team-1', role: 'editor' } as ProjectOverview)
const setup = () => renderHook(() => useWorkspace(), { wrapper: WorkspaceProvider })
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); mocks.search = {}; mocks.teamsLoading = false; mocks.team = { uuid: 'team-1' } })

describe('Project scope boundaries', () => {
  it('opening the project picker outside a project preserves the current attachments', () => {
    const { result } = setup()
    act(() => result.current.setSelectedDocUuids(['doc-a']))
    const before = result.current.newChatSignal
    act(() => result.current.deactivateProject())
    expect(result.current.selectedDocUuids).toEqual(['doc-a'])
    expect(result.current.newChatSignal).toBe(before)
  })
  it('clears chat, KBs, files, pending messages and persisted scope on exit', () => {
    const { result } = setup()
    act(() => result.current.activateProject('a', 'A'))
    act(() => {
      result.current.attachKBs([{ uuid: 'kb-a', title: 'KB A' }])
      result.current.setSelectedDocUuids(['doc-a'])
      result.current.setSelectedFolderUuids(['folder-a'])
      result.current.sendChatMessage('Old project question')
    })
    const before = result.current.newChatSignal
    act(() => result.current.deactivateProject())
    expect(result.current.activeProjectUuid).toBeNull()
    expect(result.current.activeKBs).toEqual([])
    expect(result.current.selectedDocUuids).toEqual([])
    expect(result.current.selectedFolderUuids).toEqual([])
    expect(result.current.pendingChatMessage).toBeNull()
    expect(result.current.newChatSignal).toBe(before + 1)
    expect(localStorage.getItem('workspace:project')).toBeNull()
  })
  it('ignores a slow project link after a newer project has opened', async () => {
    let finishA!: (value: ProjectOverview) => void
    mocks.getProject.mockImplementation((uuid: string) => uuid === 'a' ? new Promise(resolve => { finishA = resolve }) : Promise.resolve(project(uuid)))
    mocks.search = { project: 'a' }
    const { result, rerender } = setup()
    await waitFor(() => expect(mocks.getProject).toHaveBeenCalledWith('a'))
    mocks.search = { project: 'b' }; rerender()
    await waitFor(() => expect(result.current.activeProjectUuid).toBe('b'))
    await act(async () => { finishA(project('a')) })
    expect(result.current.activeProjectRootFolder).toBe('root-b')
    expect(localStorage.getItem('workspace:project')).toBe('b')
  })
  it('does not restore an old project or metadata after leaving', async () => {
    let finish!: (value: ProjectOverview) => void
    localStorage.setItem('workspace:project', 'a')
    mocks.getProject.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { result } = setup()
    await waitFor(() => expect(mocks.getProject).toHaveBeenCalledWith('a'))
    act(() => result.current.deactivateProject())
    await act(async () => { finish(project('a')) })
    expect(result.current.activeProjectUuid).toBeNull()
    expect(result.current.activeProjectRootFolder).toBeNull()
  })
  it('ignores metadata refreshes started before or invoked after a project switch', async () => {
    const { result } = setup()
    act(() => result.current.activateProject('a', 'A'))
    const refreshA = result.current.refreshActiveProject
    let finish!: (value: ProjectOverview) => void
    mocks.getProject.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    act(() => refreshA())
    await waitFor(() => expect(mocks.getProject).toHaveBeenCalledWith('a'))
    act(() => result.current.activateProject('b', 'B'))
    await act(async () => { finish(project('a')) })
    expect(result.current.activeProjectTitle).toBe('B')
    expect(result.current.activeProjectRootFolder).toBeNull()
    act(() => refreshA())
    expect(mocks.getProject).toHaveBeenCalledTimes(1)
  })
  it('does not reset navigation when the initial team finishes loading', () => {
    mocks.teamsLoading = true
    mocks.search = { mode: 'projects' }
    const { result, rerender } = setup()
    mocks.teamsLoading = false
    rerender()
    expect(result.current.workspaceMode).toBe('projects')
    expect(mocks.navigate).not.toHaveBeenCalled()
  })
  it('clears selection and conversation when the team changes', () => {
    const { result, rerender } = setup()
    act(() => { result.current.activateProject('a', 'A'); result.current.setSelectedDocUuids(['a']) })
    const before = result.current.newChatSignal
    mocks.team = { uuid: 'team-2' }; rerender()
    expect(result.current.activeProjectUuid).toBeNull()
    expect(result.current.selectedDocUuids).toEqual([])
    expect(result.current.newChatSignal).toBe(before + 1)
  })
  it('reports inaccessible project links and clears the previous scope', async () => {
    const { result, rerender } = setup()
    act(() => result.current.activateProject('a', 'A'))
    mocks.getProject.mockRejectedValue(new Error('Forbidden'))
    mocks.search = { project: 'forbidden' }; rerender()
    await waitFor(() => expect(mocks.toast).toHaveBeenCalledWith(expect.stringContaining('Could not open this project'), 'error'))
    expect(result.current.activeProjectUuid).toBeNull()
  })
})
