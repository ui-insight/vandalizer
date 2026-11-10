import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApprovalQueueContext, approvalStep, isPlainApproval, typedApprovalTarget, waitingActions, whichOneQuestion } from './approvalSteps'
import { planFinishLine } from './PlanChecklist'
import { collapseDetails, detailsAsText } from './markdown'
import { copyMessages, conversationToText } from './conversationExport'
import { ToolStatusLine } from './ToolCallDisplay'
import type { ChatMessage, PlanTask } from '../../types/chat'

// Support ticket: setting up a subaward left Move files, Add to inbox and Save
// page waiting at once, "Yes, go ahead" didn't say which card it approved, and
// the next action was buried in long replies with no clear finish.

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

const plan = (statuses: PlanTask['status'][]): PlanTask[] =>
  statuses.map((status, i) => ({ content: `Task ${i + 1}`, active_form: `Doing ${i + 1}`, status }))

describe('approvalStep', () => {
  it('numbers the current card from the plan', () => {
    const queue = { pending: ['move', 'inbox'], plan: plan(['completed', 'awaiting_approval', 'awaiting_approval', 'pending', 'pending']) }
    expect(approvalStep('move', queue)).toEqual({ position: 0, current: true, heading: 'Step 2 of 5' })
    expect(approvalStep('inbox', queue)).toEqual({ position: 1, current: false, heading: 'Step 3 of 5' })
    expect(approvalStep('done-already', queue)).toBeNull()
  })

  it('numbers by the queue without a plan, and not at all for a lone card', () => {
    expect(approvalStep('b', { pending: ['a', 'b'], plan: null })?.heading).toBe('Step 2 of 2')
    expect(approvalStep('a', { pending: ['a'], plan: null })?.heading).toBe('')
  })
})

describe('isPlainApproval', () => {
  it.each(['Yes, go ahead', 'yes', 'OK do it', 'Approve', 'sure, please proceed', 'Yes please!', 'go ahead'])('%s is a bare yes', text => {
    expect(isPlainApproval(text)).toBe(true)
  })
  it.each(['No, cancel that', 'yes but change the title', "don't", 'add the deadlines', 'what is due next?', ''])('%s is not', text => {
    expect(isPlainApproval(text)).toBe(false)
  })
})

const cards: ChatMessage = {
  role: 'assistant', content: 'Ready.',
  tool_results: [
    { tool_name: 'move_documents_to_project', tool_call_id: 'move', content: { needs_confirmation: true, preview: 'Move 1 file' }, quality: null },
    { tool_name: 'propose_obligations', tool_call_id: 'inbox1', content: { needs_confirmation: true, preview: 'Add 3 deadlines' }, quality: null },
    { tool_name: 'propose_obligations', tool_call_id: 'inbox2', content: { needs_confirmation: true }, quality: null },
    { tool_name: 'create_html_artifact', tool_call_id: 'page', content: { needs_confirmation: true, preview_id: 'pv1' }, quality: null },
  ],
}

describe('waitingActions', () => {
  it('lists the waiting cards in queue order, with distinct button names', () => {
    const actions = waitingActions([cards], ['inbox1', 'page', 'inbox2'])
    expect(actions.map(a => a.label)).toEqual(['Add to inbox (1)', 'Save page', 'Add to inbox (2)'])
    expect(actions[0].detail).toBe('Add 3 deadlines')
    expect(actions[1].pageApproval).toBe('pv1')
  })

  it('asks which one by button name', () => {
    expect(whichOneQuestion([{ id: 'a', label: 'Add to inbox' }, { id: 'b', label: 'Save page' }])).toBe('Which one: Add to inbox or Save page?')
    expect(whichOneQuestion([{ id: 'a', label: 'Move files' }, { id: 'b', label: 'Add to inbox' }, { id: 'c', label: 'Save page' }]))
      .toBe('Which one: Move files, Add to inbox or Save page?')
  })
})

describe('a typed yes', () => {
  it('approves the current step, the one card with buttons', () => {
    const target = typedApprovalTarget('Yes, go ahead', [cards], ['move', 'inbox1', 'page'])
    expect(target).toEqual({ approve: expect.objectContaining({ id: 'move', label: 'Move files' }) })
  })

  it('approves a Page step with its stored preview', () => {
    expect(typedApprovalTarget('ok', [cards], ['page', 'move'])).toEqual({ approve: expect.objectContaining({ id: 'page', pageApproval: 'pv1' }) })
  })

  it('asks which one only when the current step is not in this chat', () => {
    const target = typedApprovalTarget('yes', [cards], ['not-loaded', 'move', 'inbox1'])
    expect(target && 'ask' in target && target.ask.map(a => a.id)).toEqual(['move', 'inbox1'])
  })

  it('leaves other messages, and chats with nothing waiting, to the Assistant', () => {
    expect(typedApprovalTarget('yes but rename it', [cards], ['move'])).toBeNull()
    expect(typedApprovalTarget('yes', [cards], [])).toBeNull()
    expect(typedApprovalTarget('yes', [cards], ['not-loaded'])).toBeNull()
  })
})

describe('one card at a time', () => {
  const card = (id: string, tool: string, preview: string) => {
    const call = { tool_name: tool, tool_call_id: id, args: {} }
    return { call, result: { ...call, content: { needs_confirmation: true, preview }, quality: null } }
  }
  const queue = { pending: ['move', 'inbox'], plan: plan(['completed', 'awaiting_approval', 'awaiting_approval', 'pending', 'pending']) }

  it('the current step has Approve and Skip; the next one has no buttons', () => {
    const onConfirm = vi.fn()
    const move = card('move', 'move_documents_to_project', 'Move the PDF into the project')
    const inbox = card('inbox', 'propose_obligations', 'Add 3 deadlines')
    render(<ApprovalQueueContext.Provider value={queue}>
      <ToolStatusLine {...move} onConfirm={onConfirm} />
      <ToolStatusLine {...inbox} onConfirm={onConfirm} />
    </ApprovalQueueContext.Provider>)
    expect(screen.getByText('Step 2 of 5: Move files')).toBeInTheDocument()
    expect(screen.getByText(/Step 3 of 5 · Up next/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to inbox' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(onConfirm).toHaveBeenCalledWith('No, cancel that', undefined, { decline: 'move' })
  })

  it('a lone card outside a plan keeps Cancel action', () => {
    const move = card('move', 'move_documents_to_project', 'Move 1 file')
    render(<ApprovalQueueContext.Provider value={{ pending: ['move'], plan: null }}>
      <ToolStatusLine {...move} onConfirm={vi.fn()} />
    </ApprovalQueueContext.Provider>)
    expect(screen.getByRole('button', { name: 'Move files' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel action' })).toBeInTheDocument()
  })
})

describe('a clear finish', () => {
  it('reads each step’s result, falling back to its name', () => {
    const tasks: PlanTask[] = [
      { content: 'Create project', active_form: '', status: 'completed', result: 'project created' },
      { content: 'Add deadlines', active_form: '', status: 'completed', result: '3 deadlines added, 2 need your help' },
      { content: 'Save page', active_form: '', status: 'completed', result: 'Page saved.' },
      { content: 'Extract details', active_form: '', status: 'completed' },
    ]
    expect(planFinishLine(tasks)).toBe('Done: project created, 3 deadlines added, 2 need your help, Page saved, Extract details.')
  })
})

describe('short replies', () => {
  it('collapses a :::details block under Show details', () => {
    const out = collapseDetails('Moved the PDF. Next: add 3 deadlines.\n:::details\n| a | b |\n|---|---|\n| 1 | 2 |\n:::\nThanks.')
    expect(out).toContain('<details class="chat-reply-details"><summary>Show details</summary>\n\n| a | b |')
    expect(out.startsWith('Moved the PDF. Next: add 3 deadlines.\n<details')).toBe(true)
    expect(out).toContain('</details>\n\nThanks.')
  })

  it('copy and export read the block as a Details section, not raw markers', () => {
    const reply = 'Moved the PDF. Next: add 3 deadlines.\n:::details\nThe PDF was 12 pages.\n:::'
    expect(detailsAsText(reply)).toBe('Moved the PDF. Next: add 3 deadlines.\n\nDetails:\nThe PDF was 12 pages.\n')
    const messages: ChatMessage[] = [{ role: 'assistant', content: reply }]
    for (const text of [copyMessages(messages), conversationToText(messages)]) {
      expect(text).toContain('Details:\nThe PDF was 12 pages.')
      expect(text).not.toContain(':::')
    }
  })

  it('an unclosed block runs to the end of the reply', () => {
    expect(collapseDetails('Done.\n:::details\nline 1\nline 2')).toContain('line 1\nline 2\n\n</details>')
  })
})
