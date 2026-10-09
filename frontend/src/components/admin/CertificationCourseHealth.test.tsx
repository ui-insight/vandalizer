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
