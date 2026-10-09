import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CertificationLearnerSummary } from './CertificationLearnerSummary'
import type { CertificationProgressDetail, CertificationSupportSummary } from '../../api/admin'
const get = vi.fn()
vi.mock('../../api/admin', () => ({ getCertificationProgressDetail: (...args: unknown[]) => get(...args) }))
const item: CertificationProgressDetail = {
  user_id: 'learner', progress_id: 'progress', enrollment_id: 'enrollment', course_version: 'original', course_title: 'Original course',
  name: 'Alex', email: null, level: 'novice', total_xp: 100, modules_completed: 1, modules_total: 11, certified: false,
  certified_at: null, last_activity_date: null, unlocked: false, updated_at: null, modules: {}, is_active: true,
}
const summary: CertificationSupportSummary = {
  read_only: true, observed_at: '2026-10-08T00:00:00+00:00', position_status: 'saved',
  last_saved_lesson: { module_id: 'ai', module_title: 'AI Literacy', lesson_id: 'intro', lesson_title: 'Introduction', revision: 2, saved_at: null },
  pending_credential: false, explanation: 'Opening this view does not grade or change a course.', pending_completions: [], recent_completions: [], older_completions_available: false,
}
beforeEach(() => { get.mockReset().mockResolvedValue({ ...item, support_summary: summary }) })
it('shows original course, saved lesson and credit separately without assessment controls', async () => {
  const close = vi.fn()
  render(<CertificationLearnerSummary item={item} onClose={close} />)
  expect(await screen.findByText('AI Literacy · Introduction')).toBeInTheDocument()
  expect(get).toHaveBeenCalledWith('learner', 'enrollment')
  expect(screen.getByText('1/11 modules · 100 XP')).toBeInTheDocument()
  expect(screen.getByText(/Reading position does not establish assessment credit/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /grade|recover|issue/i })).toBeNull()
  expect(screen.getByRole('region', { name: 'Learning status: Alex' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Close status' }))
  expect(close).toHaveBeenCalledOnce()
})
it('displays failed required outcomes and exact selected receipts', async () => {
  get.mockResolvedValue({ ...item, is_active: false, support_summary: { ...summary, pending_credential: true, older_completions_available: true,
    pending_completions: [{ attempt_id: 'p', module_id: 'ai', module_title: 'AI Literacy', state: 'evaluating', in_flight: true, next_step: 'Inspect the original request before retrying.' }],
    recent_completions: [{ attempt_id: 'a'.repeat(32), module_title: 'AI Literacy', state: 'rejected', next_step: 'Revise the selected evidence.', selected_evidence: { review_attempt_id: 'b'.repeat(32), scenario_attempt_id: 'c'.repeat(32) }, failed_required_outcomes: [{ outcome_id: 'o', statement: 'Explain the limits of generated answers.' }] }],
  } })
  render(<CertificationLearnerSummary item={item} onClose={vi.fn()} />)
  expect(await screen.findByText('Preserved course history')).toBeInTheDocument()
  expect(screen.getByText('Explain the limits of generated answers.')).toBeInTheDocument()
  expect(screen.getByText(/worker is still marked in flight/)).toBeInTheDocument()
  expect(screen.getByText(/credential issuance record is pending/)).toBeInTheDocument()
  expect(screen.getByText('b'.repeat(32))).toBeInTheDocument()
  expect(screen.getByText(/Older completion requests exist/)).toBeInTheDocument()
})
it.each(['user_id', 'progress_id', 'enrollment_id', 'course_version'] as const)('rejects mismatched %s', async field => {
  get.mockResolvedValue({ ...item, [field]: 'wrong', support_summary: summary })
  render(<CertificationLearnerSummary item={item} onClose={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('The course record changed')
  expect(screen.queryByText('AI Literacy · Introduction')).toBeNull()
})
it('clears stale data during refresh and allows retry after a read failure', async () => {
  render(<CertificationLearnerSummary item={item} onClose={vi.fn()} />)
  await screen.findByText('AI Literacy · Introduction')
  let fail!: (error: Error) => void
  get.mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh learning status' }))
  expect(screen.queryByText('AI Literacy · Introduction')).toBeNull()
  expect(screen.getByRole('status')).toHaveTextContent('Loading saved')
  fail(new Error('Read unavailable'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Read unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh learning status' }))
  expect(await screen.findByText('AI Literacy · Introduction')).toBeInTheDocument()
  expect(get).toHaveBeenCalledTimes(3)
})
it('labels legacy and unavailable positions without inventing history', async () => {
  const legacy = { ...item, enrollment_id: null, course_version: null, is_active: null }
  get.mockResolvedValue({ ...legacy, support_summary: { ...summary, position_status: 'unavailable', last_saved_lesson: null } })
  render(<CertificationLearnerSummary item={legacy} onClose={vi.fn()} />)
  expect(await screen.findByText('Historical version unknown')).toBeInTheDocument()
  expect(get).toHaveBeenCalledWith('learner', undefined)
  expect(screen.getByText(/could not be matched to the original lesson/)).toBeInTheDocument()
  expect(screen.getByText(/No module completion requests are recorded/)).toBeInTheDocument()
})
