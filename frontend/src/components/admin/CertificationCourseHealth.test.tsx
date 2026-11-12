import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { CertificationCourseHealth } from './CertificationCourseHealth'
import type { CertificationHealthReport } from '../../api/certificationHealth'

const get = vi.fn()
vi.mock('../../api/certificationHealth', () => ({ getCertificationHealth: () => get() }))
const report: CertificationHealthReport = {
  read_only: true, scope: 'all_retained_records', started_at: '2026-10-09T00:00:00Z', observed_at: '2026-10-09T00:00:01Z',
  unavailable_metrics: ['bridge_uptake', 'grading_disputes', 'abandonment_rate'],
  rows: [{ source: 'automatic_reviews', course_version: 'course-v5', manifest_sha256: 'a'.repeat(64), state: 'unavailable', provenance: null, count: 2 },
    { source: 'enrollments', course_version: 'course-v5', manifest_sha256: 'b'.repeat(64), state: 'prepared', provenance: 'explicit_upgrade', count: 1 },
    { source: 'enrollments', course_version: null, manifest_sha256: null, state: 'active', provenance: 'legacy_version_unknown', count: 3 }],
}
beforeEach(() => get.mockReset().mockResolvedValue(report))
function open() { fireEvent.click(screen.getByText('Course health by version')) }

it('separates a bounded client observation window from saved states and missing rates', async () => {
  get.mockResolvedValue({ ...report, journey: { window_days: 30, source: 'client_observation',
    window_started_at: report.started_at, window_ended_at: report.observed_at,
    rows: [{ source: 'client_journey', course_version: 'course-v5', manifest_sha256: 'a'.repeat(64), state: 'position_save_failed', provenance: null, count: 2 }] } })
  render(<CertificationCourseHealth />); open()
  expect(await screen.findByText('Reading-place save failed: 2')).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Client-reported learning journeys' })).toHaveTextContent('last 30 days')
  expect(screen.getByText(/Offline browsers and older app versions can miss events/)).toBeInTheDocument()
})

it('shows journey outcomes by course title, withholds small-sample rates and keeps hashes in support details', async () => {
  const course = { course_version: 'course-v5', manifest_sha256: 'a'.repeat(64), course_title: 'Research Workflow Practitioner',
    started: 8, active: 3, completed: 2, transferred: 1, inactive: 1, activity_unknown: 0, staff_grading_corrections: 1,
    grading_questions_opened: 3, resumes_restored: 4, resumes_unavailable: 1, completion_rate: 2 / 7, inactive_share: null, resume_success_rate: 0.8 }
  get.mockResolvedValue({ ...report, unavailable_metrics: ['dropout', 'grading_question_outcomes'], journey_success: {
    inactive_after_days: 60, min_rate_denominator: 5, journey_window_days: 30, courses: [course],
    bridge: { legacy_learners: 5, upgraded_learners: 2, uptake_rate: 0.4, targets: [{ course_version: 'course-v5', manifest_sha256: 'a'.repeat(64), course_title: 'Research Workflow Practitioner', learners: 2 }] } } })
  render(<CertificationCourseHealth />); open()
  const outcomes = await screen.findByRole('region', { name: 'Journey outcomes: Research Workflow Practitioner (version course-v5)' })
  expect(outcomes).toHaveTextContent('Completed: 2 · 28.6%')
  expect(outcomes).toHaveTextContent('1 transferred to another course and excluded')
  expect(outcomes).toHaveTextContent('Inactive 60+ days: 1 of 3 active · rate withheld (too few records)')
  expect(outcomes).toHaveTextContent('Resumed at saved place: 4 of 5 · 80%')
  expect(outcomes).toHaveTextContent('Grading questions opened: 3')
  expect(outcomes).toHaveTextContent('Staff grading corrections: 1')
  expect(screen.getByRole('region', { name: 'Bridge uptake' })).toHaveTextContent('2 of 5 learners with a historical course record started a newer course (40%)')
  expect(screen.getByText(/It is not dropout/)).toBeInTheDocument()
  expect(screen.getByText(/Why learners stop \(dropout\), Whether a grading question was upheld/)).toBeInTheDocument()
  expect(screen.getAllByRole('heading', { name: 'Research Workflow Practitioner (version course-v5)' }).length).toBeGreaterThan(1)
  for (const hash of screen.getAllByText(/Package: a{64}/)) expect(hash.closest('details')).not.toBeNull()
})

it('loads only when opened and separates package identities and unknown history', async () => {
  render(<CertificationCourseHealth />)
  expect(get).not.toHaveBeenCalled()
  open()
  expect(await screen.findByText('Automatic reviews')).toBeInTheDocument()
  expect(screen.getAllByRole('region', { name: 'Course health: course-v5' })).toHaveLength(2)
  expect(screen.getByText('Historical or missing course version')).toBeInTheDocument()
  expect(screen.getByText(/Missing event history is unavailable, not zero/)).toBeInTheDocument()
  expect(screen.getByText(/Prepared enrollments are not starts/)).toBeInTheDocument()
  expect(get).toHaveBeenCalledOnce()
})
it('removes prior counts during refresh and reports read failure with a usable retry', async () => {
  render(<CertificationCourseHealth />); open()
  await screen.findByText('Automatic reviews')
  get.mockRejectedValueOnce(new Error('Course health is unavailable. Retry the report.'))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh course health' }))
  expect(screen.queryByText('Automatic reviews')).toBeNull()
  expect(await screen.findByRole('alert')).toHaveTextContent('Course health is unavailable')
  expect(screen.queryByText(/No records were found/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh course health' }))
  expect(await screen.findByText('Automatic reviews')).toBeInTheDocument()
})
it('keeps empty collections distinct from metrics without instrumentation', async () => {
  get.mockResolvedValue({ ...report, rows: [] })
  render(<CertificationCourseHealth />); open()
  expect(await screen.findByText('No records were found in the four monitored collections.')).toBeInTheDocument()
  expect(screen.getByText(/Bridge uptake, Grading disputes, Abandonment rate/)).toBeInTheDocument()
})
it('ignores a response from a closed report when it is reopened', async () => {
  let resolve!: (value: CertificationHealthReport) => void
  get.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  render(<CertificationCourseHealth />); open()
  await waitFor(() => expect(get).toHaveBeenCalledOnce())
  open()
  await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
  open()
  await screen.findByText('Automatic reviews')
  resolve({ ...report, rows: [] })
  await waitFor(() => expect(screen.queryByText(/No records were found/)).toBeNull())
})
