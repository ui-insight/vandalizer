import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import type { PracticalHistoryCourse, PracticalHistoryCourses } from '../../types/certification'
import { CourseHistory } from './CourseHistory'

vi.mock('../../api/certification', () => ({ getPracticalHistoryCourses: vi.fn(), getPracticalHistoryCourse: vi.fn() }))
vi.mock('./PracticalReview', () => ({ PracticalReview: (props: { enrollmentId: string; moduleId: string; historyOnly: boolean }) => <div data-testid="practical">{JSON.stringify(props)}</div> }))
const id = 'a'.repeat(32)
const listing: PracticalHistoryCourses = { read_only: true, older_courses_available: false, courses: [{ enrollment_id: id, course_version: 'original', course_title: 'Original course', enrollment_state: 'transferred', created_at: null, definition_available: true }] }
const course: PracticalHistoryCourse = { enrollment_id: id, course_version: 'original', course_title: 'Original course', enrollment_state: 'transferred', manifest_sha256: 'b'.repeat(64), read_only: true,
  modules: [{ module_id: 'foundations', title: 'Foundations', decision_prompts: [{ id: 'scope', module_id: 'foundations', revision: 1, outcome_id: 'scope', phase: 'before_execution', question: 'Review scope', choices: {}, required_fields: [], prompt_sha256: 'c'.repeat(64) }] }] }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.getPracticalHistoryCourses).mockResolvedValue(listing); vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue(course) })
async function open() { fireEvent.click(screen.getByRole('button', { name: 'Browse saved course work' })); await screen.findByLabelText('Saved course') }
async function inspect() { await open(); await act(async () => { fireEvent.change(screen.getByLabelText('Saved course'), { target: { value: id } }) }) }

it.each([
  ['completed', 'Recorded as completed. Your original earned work stays in this course; a newer course has its own requirements.'],
  ['transferred', 'Closed transfer history. This enrollment is read-only. Its saved work and original certificates remain preserved.'],
  ['abandoned', 'Closed course history. This enrollment is no longer open for learning. Its saved work and original certificates remain preserved.'],
])('explains %s lifecycle separately from which course is selected', async (state, message) => {
  vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue({ ...course, enrollment_state: state, selection_status: 'retained' })
  render(<CourseHistory />); await inspect()
  expect(screen.getByText('original · Retained course')).toBeInTheDocument()
  expect(screen.getByText(message)).toBeInTheDocument()
})

it('loads only on request, opens the original course and passes a read-only review boundary', async () => {
  render(<CourseHistory />)
  expect(api.getPracticalHistoryCourses).not.toHaveBeenCalled()
  await inspect()
  const result = await screen.findByRole('region', { name: 'Original course history' })
  expect(result).toHaveFocus()
  expect(api.getPracticalHistoryCourse).toHaveBeenCalledWith(id)
  fireEvent.change(screen.getByLabelText('Saved module'), { target: { value: 'foundations' } })
  expect(screen.getByTestId('practical')).toHaveTextContent('"historyOnly":true')
  expect(screen.getByTestId('practical')).toHaveTextContent(id)
  fireEvent.click(screen.getByRole('button', { name: 'Close saved course work' }))
  expect(screen.getByRole('button', { name: 'Browse saved course work' })).toHaveFocus()
  expect(screen.queryByTestId('practical')).not.toBeInTheDocument()
})
it('keeps an empty enrollment history separate from initialization', async () => {
  vi.mocked(api.getPracticalHistoryCourses).mockResolvedValue({ ...listing, courses: [] })
  render(<CourseHistory />); fireEvent.click(screen.getByRole('button', { name: 'Browse saved course work' }))
  expect(await screen.findByText('No saved course enrollments are available yet.')).toBeInTheDocument()
  expect(api.getPracticalHistoryCourse).not.toHaveBeenCalled()
})
it('opens older history by full reference and shows bounded-list guidance', async () => {
  vi.mocked(api.getPracticalHistoryCourses).mockResolvedValue({ ...listing, older_courses_available: true })
  render(<CourseHistory />); await open()
  expect(screen.getByText(/50 most recent/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Full enrollment reference'), { target: { value: id } })
  fireEvent.submit(screen.getByRole('button', { name: 'Open original course' }).closest('form')!)
  await screen.findByRole('region', { name: 'Original course history' })
  expect(api.getPracticalHistoryCourse).toHaveBeenCalledWith(id)
})
it.each(['identity', 'writable', 'digest', 'prompt'])('rejects mismatched %s history', async mismatch => {
  const wrong = structuredClone(course)
  if (mismatch === 'identity') wrong.enrollment_id = 'foreign'
  if (mismatch === 'writable') Object.assign(wrong, { read_only: false })
  if (mismatch === 'digest') wrong.manifest_sha256 = 'invalid'
  if (mismatch === 'prompt') wrong.modules[0].decision_prompts = [{ module_id: 'foreign' } as never]
  vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue(wrong)
  render(<CourseHistory />); await inspect()
  expect(await screen.findByRole('alert')).toHaveTextContent('original course could not be opened')
  expect(screen.queryByRole('region', { name: 'Original course history' })).not.toBeInTheDocument()
})
it('ignores a late course result after close', async () => {
  let finish!: (value: PracticalHistoryCourse) => void
  vi.mocked(api.getPracticalHistoryCourse).mockReturnValue(new Promise(resolve => { finish = resolve }))
  render(<CourseHistory />); await inspect()
  fireEvent.click(screen.getByRole('button', { name: 'Close saved course work' }))
  await act(async () => finish(course))
  expect(screen.queryByRole('region', { name: 'Original course history' })).not.toBeInTheDocument()
})
it('clears earlier history on reload and recovers from a list error', async () => {
  render(<CourseHistory />); await inspect(); await screen.findByRole('region', { name: 'Original course history' })
  vi.mocked(api.getPracticalHistoryCourses).mockRejectedValueOnce(new Error('Offline'))
  fireEvent.click(screen.getByRole('button', { name: 'Reload course history' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Original course history' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Reload course history' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(await screen.findByLabelText('Saved course')).toBeInTheDocument()
})
it('explains unavailable definitions and courses without practical review modules', async () => {
  vi.mocked(api.getPracticalHistoryCourses).mockResolvedValue({ ...listing, courses: [{ ...listing.courses[0], definition_available: false }] })
  vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue({ ...course, modules: [] })
  render(<CourseHistory />); await inspect()
  expect(screen.getByRole('option', { name: /definition unavailable/ })).toBeInTheDocument()
  expect(await screen.findByText(/no saved assessment review modules/)).toBeInTheDocument()
  expect(screen.queryByTestId('practical')).not.toBeInTheDocument()
})

it('ignores a late listing after unmount and keeps a later session empty', async () => {
  let finish!: (value: PracticalHistoryCourses) => void
  vi.mocked(api.getPracticalHistoryCourses).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const previous = render(<CourseHistory />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved course work' }))
  previous.unmount(); render(<CourseHistory />)
  await act(async () => finish(listing))
  expect(screen.queryByLabelText('Saved course')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Browse saved course work' })).toBeInTheDocument()
})

it('explains unknown historical provenance without relabeling older achievement', async () => {
  vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue({ ...course, provenance: 'legacy_version_unknown' })
  render(<CourseHistory />); await inspect()
  expect(await screen.findByText(/earlier course version was not recorded/)).toHaveTextContent('does not identify the lessons you previously completed')
})

it.each([
  ['prepared', 'Prepared course — not started'], ['current', 'Current course'],
  ['confirmation_pending', 'Selection awaiting confirmation'], ['retained', 'Retained course'],
] as const)('distinguishes %s course history without activating it', async (selection_status, label) => {
  vi.mocked(api.getPracticalHistoryCourses).mockResolvedValue({ ...listing, courses: [{ ...listing.courses[0], selection_status }] })
  vi.mocked(api.getPracticalHistoryCourse).mockResolvedValue({ ...course, selection_status })
  render(<CourseHistory />); await inspect()
  const original = await screen.findByRole('region', { name: 'Original course history' })
  expect(screen.getByRole('option', { name: new RegExp(label) })).toBeInTheDocument()
  expect(original).toHaveTextContent(label)
  if (selection_status === 'prepared') expect(original).toHaveTextContent('Preparation does not award credit')
  if (selection_status === 'confirmation_pending') expect(original).toHaveTextContent('Finish confirming it')
  fireEvent.change(screen.getByLabelText('Saved module'), { target: { value: 'foundations' } })
  expect(screen.getByTestId('practical')).toHaveTextContent('"historyOnly":true')
})
