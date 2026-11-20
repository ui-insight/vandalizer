import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SupportChatPanel } from './SupportChatPanel'
import { openSupportDraft } from '../../utils/supportPanel'

const api = vi.hoisted(() => ({ listTickets: vi.fn(), createTicket: vi.fn() }))
vi.mock('../../api/support', () => api)
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'learner' } }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))

const context = { key: 'assessment-1', subject: 'Completion needs review', message: 'Assessment reference: assessment-1' }
beforeEach(() => { vi.resetAllMocks(); api.listTickets.mockResolvedValue({ tickets: [] }) })

it('opens an editable draft without sending, preserving it across close and reopen', async () => {
  const panel = render(<SupportChatPanel open={false} onClose={vi.fn()} />)
  act(() => openSupportDraft(context))
  panel.rerender(<SupportChatPanel open onClose={vi.fn()} />)
  expect(await screen.findByLabelText('Subject')).toHaveValue(context.subject)
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: `${context.message}\nMy details` } })
  panel.rerender(<SupportChatPanel open={false} onClose={vi.fn()} />)
  act(() => openSupportDraft(context))
  panel.rerender(<SupportChatPanel open onClose={vi.fn()} />)
  expect(screen.getByLabelText('Description')).toHaveValue(`${context.message}\nMy details`)
  expect(api.createTicket).not.toHaveBeenCalled()
})

it('appends references while preserving existing text, options and attachments', async () => {
  render(<SupportChatPanel open onClose={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Create your first ticket' }))
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'My unfinished request' } })
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Keep these details.' } })
  fireEvent.change(screen.getByLabelText('Priority'), { target: { value: 'high' } })
  const file = new File(['synthetic'], 'notes.txt', { type: 'text/plain' })
  fireEvent.change(screen.getByLabelText('Upload files'), { target: { files: [file] } })
  act(() => openSupportDraft(context))
  expect(screen.getByLabelText('Subject')).toHaveValue('My unfinished request')
  expect(screen.getByLabelText('Description')).toHaveValue(`Keep these details.\n\n${context.message}`)
  expect(screen.getByLabelText('Priority')).toHaveValue('high')
  expect(screen.getByText('notes.txt')).toBeInTheDocument()
  expect(api.createTicket).not.toHaveBeenCalled()
})

it('holds new context until an outgoing request settles, preserving a failed draft', async () => {
  let reject!: (error: Error) => void
  api.createTicket.mockImplementation(() => new Promise((_, fail) => { reject = fail }))
  render(<SupportChatPanel open onClose={vi.fn()} />)
  act(() => openSupportDraft(context))
  fireEvent.click(screen.getByRole('button', { name: 'Submit Ticket' }))
  await waitFor(() => expect(api.createTicket).toHaveBeenCalledTimes(1))
  act(() => openSupportDraft({ ...context, key: 'assessment-2', message: 'Assessment reference: assessment-2' }))
  expect(screen.getByLabelText('Description')).toHaveValue(context.message)
  await act(async () => reject(new Error('Synthetic failure')))
  expect(screen.getByLabelText('Description')).toHaveValue(`${context.message}\n\nAssessment reference: assessment-2`)
  expect(api.createTicket).toHaveBeenCalledTimes(1)
})
