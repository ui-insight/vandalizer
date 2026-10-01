import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { DemoTab } from './DemoTab'
const mocks = vi.hoisted(() => ({ toast: vi.fn(), confirm: vi.fn().mockResolvedValue(true), resend: vi.fn().mockResolvedValue({ ok: false, status: 'send_failed', message: 'The sign-in email was not sent.' }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => mocks.confirm }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))
vi.mock('../../api/demo', () => ({
  getDemoStats: vi.fn().mockResolvedValue({ total_applications: 1, active_count: 1, waitlist_count: 0, expired_count: 0, completed_count: 0, by_organization: [] }),
  getDemoApplications: vi.fn().mockResolvedValue([{ uuid: 'trial-1', name: 'Research reviewer', email: 'reviewer@example.test', organization: 'Research office', status: 'active', questionnaire_responses: {}, tokens_used: 1, tokens_budget: 1000, user_is_demo: true }]),
  getPostExperienceResponses: vi.fn().mockResolvedValue([]), adminResendCredentials: mocks.resend,
}))
vi.mock('../../api/support', () => ({ listTickets: vi.fn().mockResolvedValue({ tickets: [] }) }))
vi.mock('../../api/feedbackPrompt', () => ({ getAdminPromptOverview: vi.fn().mockResolvedValue([]) }))
it('reports an API-declared email failure instead of announcing success', async () => {
  render(<DemoTab />)
  fireEvent.click(await screen.findByRole('button', { name: 'Resend Creds' }))
  await vi.waitFor(() => expect(mocks.toast).toHaveBeenCalledWith('The sign-in email was not sent.', 'error'))
  expect(mocks.toast).not.toHaveBeenCalledWith(expect.anything(), 'success')
  expect(mocks.resend).toHaveBeenCalledOnce()
})
