import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ project: 'project-a' as string | null, signal: 0, team: 'team-a' as string | null, loading: false, convo: null as string | null }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ activeProjectUuid: state.project, newChatSignal: state.signal, currentConversationUuid: state.convo }) }))
vi.mock('../../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: state.team ? { uuid: state.team } : null, loading: state.loading }) }))
vi.mock('../chat/ChatPanel', () => ({ ChatPanel: ({ initialDraft, onDraftChange, conversationToLoad }: { initialDraft: string; onDraftChange: (value: string) => void; conversationToLoad: string | null }) => {
  const [text, setText] = useState(initialDraft)
  return <><input aria-label="Draft" value={text} onChange={e => { setText(e.target.value); onDraftChange(e.target.value) }} /><output aria-label="Loads">{conversationToLoad ?? 'none'}</output></>
} }))
import { AssistantTab } from './AssistantTab'
beforeEach(() => { state.project = 'project-a'; state.signal = 0; state.team = 'team-a'; state.loading = false; state.convo = null; sessionStorage.clear() })
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
it('keeps an unsent draft when the Assistant is left and reopened (#1014 item 50)', () => {
  // Opening a source, an alert or the Library unmounts the Assistant; the
  // half-written question must still be there on return.
  const first = render(<AssistantTab />)
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Is the cap direct or total?' } })
  first.unmount()
  render(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Is the cap direct or total?')
})
it('reopens each scope\'s conversation, and its attachments, on return (#1014 item 50)', () => {
  // A web link or upload attached before sending lives on the conversation,
  // so a scope round trip or leaving the workspace must reopen it.
  const { rerender, unmount } = render(<AssistantTab />)
  state.convo = 'convo-a'; rerender(<AssistantTab />)
  // Switching scope: the context still names convo-a until the old panel unmounts.
  state.project = null; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Loads')).toHaveTextContent('none')
  state.convo = null; rerender(<AssistantTab />)
  state.project = 'project-a'; state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Loads')).toHaveTextContent('convo-a')
  unmount()
  render(<AssistantTab />)
  expect(screen.getByLabelText('Loads')).toHaveTextContent('convo-a')
})
it('New Chat in the same scope forgets the scope\'s conversation', () => {
  const { rerender } = render(<AssistantTab />)
  state.convo = 'convo-a'; rerender(<AssistantTab />)
  state.signal++; rerender(<AssistantTab />)
  expect(screen.getByLabelText('Loads')).toHaveTextContent('none')
})
it('keeps the draft when the Assistant remounts after an earlier New Chat', () => {
  state.signal = 3
  const first = render(<AssistantTab />)
  fireEvent.change(screen.getByLabelText('Draft'), { target: { value: 'Still here' } })
  first.unmount()
  render(<AssistantTab />)
  expect(screen.getByLabelText('Draft')).toHaveValue('Still here')
})
