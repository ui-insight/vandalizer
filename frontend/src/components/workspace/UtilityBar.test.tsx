import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { UtilityBar } from './UtilityBar'
const mocks = vi.hoisted(() => ({ setMode: vi.fn(), reset: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ workspaceMode: 'chat', setWorkspaceMode: mocks.setMode, resetToHome: mocks.reset, activeProjectRole: null, activeProjectUuid: null, chatSplitOpen: false, setChatSplitOpen: vi.fn() }) }))
it('selecting Chat does not reset the conversation or attached documents', () => {
  render(<UtilityBar />)
  fireEvent.click(screen.getByRole('button', { name: 'Chat' }))
  expect(mocks.setMode).toHaveBeenCalledWith('chat')
  expect(mocks.reset).not.toHaveBeenCalled()
})
