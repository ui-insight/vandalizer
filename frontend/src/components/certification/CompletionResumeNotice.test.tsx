import { act, fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { CompletionResumeNotice } from './CompletionResumeNotice'
import { MODULES } from './modules'
import { SupportChatPanel } from '../support/SupportChatPanel'

vi.mock('../../api/support', () => ({ listTickets: vi.fn().mockResolvedValue({ tickets: [] }) }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'learner' } }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))

it('explains that explicitly resuming the original request may finish validation and save credit', () => {
  const retry = vi.fn(), open = vi.fn()
  render(<CompletionResumeNotice pending={[{ attempt_id: 'a'.repeat(32), module_id: 'foundations', state: 'uncertain', in_flight: false }]} modules={MODULES} busy={false} onOpen={open} onRetry={retry} onRefresh={vi.fn()} />)
  expect(retry).not.toHaveBeenCalled()
  expect(screen.getByText(/It may finish validation and save credit/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open module' }))
  expect(open).toHaveBeenCalledWith('foundations')
  fireEvent.click(screen.getByRole('button', { name: 'Resume original completion' }))
  expect(retry).toHaveBeenCalledWith('foundations', 'a'.repeat(32))
})

it('prepares an editable request with the exact enrollment and assessment references', async () => {
  const close = vi.fn(), retry = vi.fn()
  render(<><SupportChatPanel open onClose={vi.fn()} /><CompletionResumeNotice
    pending={[{ attempt_id: 'b'.repeat(32), module_id: 'foundations', state: 'evaluating', in_flight: false }]}
    modules={MODULES} course={{ enrollment_id: 'enrollment-1', course_version: 'version-1', course_title: 'My saved course' }}
    busy={false} onOpen={vi.fn()} onRetry={retry} onRefresh={vi.fn()} onHelp={close}
  /></>)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Prepare support request' })) })
  const description = screen.getByLabelText('Description') as HTMLTextAreaElement
  expect(description.value).toContain('Enrollment: enrollment-1')
  expect(description.value).toContain('Course version: version-1')
  expect(description.value).toContain(`Assessment reference: ${'b'.repeat(32)}`)
  expect(close).toHaveBeenCalledOnce()
  expect(retry).not.toHaveBeenCalled()
})

it.each([{ state: 'evaluating' as const, in_flight: true }, { state: 'evaluating' as const, in_flight: false }, { state: 'review' as const, in_flight: false }])('offers read-only refresh for unresolved evaluation %j', item => {
  const refresh = vi.fn()
  render(<CompletionResumeNotice pending={[{ attempt_id: 'b'.repeat(32), module_id: 'foundations', ...item }]} modules={MODULES} busy={false} onOpen={vi.fn()} onRetry={vi.fn()} onRefresh={refresh} />)
  expect(screen.queryByRole('button', { name: 'Resume original completion' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh status' }))
  expect(refresh).toHaveBeenCalledTimes(1)
})
