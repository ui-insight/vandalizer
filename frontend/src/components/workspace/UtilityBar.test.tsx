import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { UtilityBar } from './UtilityBar'
const mocks = vi.hoisted(() => ({ setMode: vi.fn(), reset: vi.fn(), mode: 'chat', project: null as string | null }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ workspaceMode: mocks.mode, setWorkspaceMode: mocks.setMode, resetToHome: mocks.reset, activeProjectRole: null, activeProjectUuid: mocks.project, chatSplitOpen: false, setChatSplitOpen: vi.fn() }) }))
beforeEach(() => { mocks.mode = 'chat'; mocks.project = null; vi.clearAllMocks() })
it('selecting Chat does not reset the conversation or attached documents', () => {
  render(<UtilityBar />)
  fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
  expect(mocks.setMode).toHaveBeenCalledWith('chat')
  expect(mocks.reset).not.toHaveBeenCalled()
})
it('identifies the chat surface when a project is opened from the project picker', () => {
  mocks.mode = 'projects'
  mocks.project = 'project-1'
  render(<UtilityBar />)
  expect(screen.getByRole('button', { name: 'Chat' }).getAttribute('aria-current')).toBe('page')
  expect(screen.getByRole('button', { name: 'Projects' }).getAttribute('aria-current')).toBeNull()
})
