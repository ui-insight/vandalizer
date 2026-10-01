import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ project: 'project-a' as string | null, signal: 0, team: 'team-a' as string | null, loading: false }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ activeProjectUuid: state.project, newChatSignal: state.signal }) }))
vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: state.team ? { uuid: state.team } : null, loading: state.loading }) }))
vi.mock('../chat/ChatPanel', () => ({ ChatPanel: ({ initialDraft, onDraftChange }: { initialDraft: string; onDraftChange: (value: string) => void }) => {
  const [text, setText] = useState(initialDraft)
  return <input aria-label="Draft" value={text} onChange={e => { setText(e.target.value); onDraftChange(e.target.value) }} />
} }))
import { AssistantTab } from './AssistantTab'
beforeEach(() => { state.project = 'project-a'; state.signal = 0; state.team = 'team-a'; state.loading = false })
it('waits for initial scope and preserves typing across background team refresh', () => {
  state.team = null; state.loading = true
  const { rerender } = render(<AssistantTab />)
  expect(screen.queryByLabelText('Draft')).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Loading conversation workspace')
  state.team = 'team-a'; state.loading = false; rerender(<AssistantTab />)
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Keep my question' } })
  state.loading = true; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Keep my question')
})
it('keeps unsent drafts separate across project and team switches and restores on return', () => {
  const { rerender } = render(<AssistantTab />)
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Project A evidence question' } })
  state.project = null; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Personal draft' } })
  state.project = 'project-a'; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Project A evidence question')
  state.team = 'team-b'; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('')
  state.team = 'team-a'; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Project A evidence question')
  state.project = null; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Personal draft')
})
it('explicit New Chat in the same scope clears its unsent draft', () => {
  const { rerender } = render(<AssistantTab />)
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Draft to discard' } })
  state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('')
})
