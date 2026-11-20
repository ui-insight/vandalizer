import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { approvalHistoryFor, hasWaitingCard } from './approvalHistory'
import { ToolStatusLine } from './ToolCallDisplay'
import type { ChatMessage } from '../../types/chat'

// Support ticket: with Move files, Add to inbox ×3 and Save to folder waiting,
// clicking Move files carried out all of them.

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

const CARDS = ['move', 'inbox1', 'inbox2', 'inbox3', 'save']
const tool = (id: string) => id === 'move' ? 'move_documents_to_project' : id === 'save' ? 'save_to_folder' : 'propose_obligations'
const previews: ChatMessage = {
  role: 'assistant', content: 'Five actions are ready for your approval.',
  tool_calls: CARDS.map(id => ({ tool_name: tool(id), tool_call_id: id, args: { card: id, confirmed: false } })),
  tool_results: CARDS.map(id => ({ tool_name: tool(id), tool_call_id: id, content: { needs_confirmation: true, preview: id }, quality: null })),
}

describe('approval card buttons', () => {
  it('approve and cancel each name their own card', () => {
    const onConfirm = vi.fn()
    const call = { tool_name: 'move_documents_to_project', tool_call_id: 'move', args: {} }
    const { unmount } = render(<ToolStatusLine call={call} result={{ ...call, content: { needs_confirmation: true, preview: 'Move 1 file' }, quality: null }} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Move files' }))
    expect(onConfirm).toHaveBeenCalledWith('Yes, go ahead', undefined, { approve: 'move' })
    unmount()
    render(<ToolStatusLine call={call} result={{ ...call, content: { needs_confirmation: true, preview: 'Move 1 file' }, quality: null }} onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel action' }))
    expect(onConfirm).toHaveBeenLastCalledWith('No, cancel that', undefined, { decline: 'move' })
  })

  it('shows a refused attempt as still waiting, not as a new card', () => {
    const call = { tool_name: 'save_to_folder', tool_call_id: 'run-save', args: { confirmed: true } }
    render(<ToolStatusLine call={call} result={{ ...call, content: { status: 'awaiting_user_confirmation', still_waiting: true, preview: 'Save' }, quality: null }} onConfirm={vi.fn()} />)
    expect(screen.getByText('Waiting for its own approval')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save to folder' })).not.toBeInTheDocument()
  })
})

describe('card history after one click', () => {
  const clicked: ChatMessage = { role: 'user', content: 'Yes, go ahead', approval_for: 'move' }
  const moved: ChatMessage = { role: 'assistant', content: 'Moved.',
    tool_calls: [{ tool_name: 'move_documents_to_project', tool_call_id: 'run-move', args: { card: 'move', confirmed: true } }],
    tool_results: [{ tool_name: 'move_documents_to_project', tool_call_id: 'run-move', content: { status: 'completed' }, quality: null }] }

  it('decides only the clicked card; the others stay clickable', () => {
    const history = approvalHistoryFor(previews, [clicked, moved], false, ['inbox1', 'inbox2', 'inbox3', 'save'])
    expect(history.move.label).toBe('Completed')
    expect(Object.keys(history)).toEqual(['move'])
  })

  it('a click decides only its card even without the server’s waiting list', () => {
    const history = approvalHistoryFor(previews, [clicked, moved], false, [])
    expect(Object.keys(history)).toEqual(['move'])
  })

  it('keeps cards clickable after a typed yes the server refused', () => {
    const typed: ChatMessage = { role: 'user', content: 'yes do them all' }
    const refused: ChatMessage = { role: 'assistant', content: 'Approve each card you want.',
      tool_calls: [{ tool_name: 'save_to_folder', tool_call_id: 'run-save', args: { card: 'save', confirmed: true } }],
      tool_results: [{ tool_name: 'save_to_folder', tool_call_id: 'run-save', content: { status: 'awaiting_user_confirmation', still_waiting: true }, quality: null }] }
    const history = approvalHistoryFor(previews, [typed, refused], false, CARDS)
    expect(history).toEqual({})
    // Without the server's list (an older chat), a refused attempt still isn't counted as done.
    expect(approvalHistoryFor(previews, [typed, refused], false, []).save.label).not.toBe('Result recorded')
  })

  it('a chat saved before cards named themselves keeps the old behaviour', () => {
    const legacy: ChatMessage = { role: 'user', content: 'Yes, go ahead' }
    const history = approvalHistoryFor(previews, [legacy, moved], false, [])
    expect(history.move.label).toBe('Completed')
    expect(history.save.label).toBe('Not done')
  })
})

describe('which earlier answers keep their buttons', () => {
  it('an answer with a card the server still has waiting stays clickable', () => {
    expect(hasWaitingCard(previews, ['save'])).toBe(true)
    expect(hasWaitingCard(previews, ['other'])).toBe(false)
    expect(hasWaitingCard(previews, [])).toBe(false)
  })
})
