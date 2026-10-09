import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import type { SavedAutomaticReview } from '../../types/certification'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'
vi.mock('../../api/certification', () => ({ getAutomaticReview: vi.fn(), getAutomaticReviews: vi.fn() }))
const saved: SavedAutomaticReview = {
  attempt_id: 'a'.repeat(32), enrollment_id: 'enrollment', module_id: 'foundations', run_id: 'b'.repeat(32),
  course_version: 'draft', manifest_sha256: 'c'.repeat(64), prepared_at: '2026-10-06', finished_at: null, parent_attempt_id: null,
  status: 'revision_required', assessment_kind: 'practical_review_draft', credit_awarded: false, module_completion_eligible: false,
  staff_review_required: false, can_request_review: false, can_retry_review: false,
  outcomes: [{ outcome_id: 'scope', statement: 'Review assigned scope', method: 'structured_review', verdict: 'unclear',
    explanation: 'The source comparison was not established.', revision_instruction: 'Compare the saved source against the assigned agency.',
    citations: [{ kind: 'decision', quote: '<script>Untrusted learner text</script>' }] }],
}
const props = { enrollmentId: 'enrollment', moduleId: 'foundations' }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getAutomaticReviews).mockResolvedValue({ enrollment_id: 'enrollment', module_id: 'foundations', attempts: [saved], older_attempts_available: false })
  vi.mocked(api.getAutomaticReview).mockResolvedValue(saved)
})
async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'View saved assessments' }))
  fireEvent.click(await screen.findByRole('button', { name: /Assessment 1/ }))
}
it('loads only on request and renders revision evidence as text without grading or staff routing', async () => {
  render(<SavedAutomaticReviews {...props} />)
  expect(api.getAutomaticReviews).not.toHaveBeenCalled()
  await open()
  expect(await screen.findByText('Compare the saved source against the assigned agency.')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Evidence cited (1)'))
  expect(screen.getByText('<script>Untrusted learner text</script>')).toBeInTheDocument()
  expect(document.querySelector('script')).toBeNull()
  expect(api.getAutomaticReview).toHaveBeenCalledWith('enrollment', saved.attempt_id)
  fireEvent.click(screen.getByRole('button', { name: 'Close assessments' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'View saved assessments' })).toHaveFocus())
})
it('calls a technical failure unavailable and preserves a separate execution check', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, status: 'grading_unavailable', outcomes: [{ ...saved.outcomes[0], method: 'deterministic', verdict: 'supported', revision_instruction: '', explanation: 'The approved assigned inputs were executed.' }] })
  render(<SavedAutomaticReviews {...props} />)
  await open()
  expect(await screen.findByText(/This is not a failed learner attempt/)).toBeInTheDocument()
  expect(screen.getByText('Execution check · Supported by saved evidence')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Retry grading|Contact staff/ })).not.toBeInTheDocument()
})
it.each([{ enrollment_id: 'foreign' }, { module_id: 'other' }, { attempt_id: 'different' }, { credit_awarded: true }])('rejects a mismatched or incompatible result %j', async changed => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, ...changed } as SavedAutomaticReview)
  render(<SavedAutomaticReviews {...props} />)
  await open()
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be opened for this course')
  expect(screen.queryByText(saved.outcomes[0].statement)).not.toBeInTheDocument()
})
it('ignores a response arriving after close', async () => {
  let resolve!: (value: SavedAutomaticReview) => void
  vi.mocked(api.getAutomaticReview).mockReturnValue(new Promise(done => { resolve = done }))
  render(<SavedAutomaticReviews {...props} />)
  await open()
  fireEvent.click(screen.getByRole('button', { name: 'Close assessments' }))
  resolve(saved)
  await waitFor(() => expect(screen.queryByText(saved.outcomes[0].statement)).not.toBeInTheDocument())
})
it('clears earlier feedback when a later read fails and permits refreshing', async () => {
  render(<SavedAutomaticReviews {...props} />)
  await open()
  await screen.findByText(saved.outcomes[0].statement)
  vi.mocked(api.getAutomaticReview).mockRejectedValueOnce(new Error('Response lost'))
  fireEvent.click(screen.getByRole('button', { name: /Assessment 1/ }))
  await screen.findByRole('alert')
  expect(screen.queryByText(saved.outcomes[0].statement)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh saved assessments' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})

it('opens an explicitly handed-off assessment and focuses the mounted feedback without listing or writing', async () => {
  render(<SavedAutomaticReviews {...props} initialAttemptId={saved.attempt_id} />)
  await screen.findByText(saved.outcomes[0].revision_instruction)
  await waitFor(() => expect(screen.getByRole('region', { name: 'Saved assessment result' })).toHaveFocus())
  expect(api.getAutomaticReviews).not.toHaveBeenCalled()
  expect(api.getAutomaticReview).toHaveBeenCalledWith('enrollment', saved.attempt_id)
  fireEvent.click(screen.getByRole('button', { name: 'Close assessments' }))
  expect(screen.getByRole('button', { name: 'View saved assessments' })).toHaveFocus()
})

it('shows an original process reference without claiming an execution', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'process_mapping', run_id: null,
    process_submission_id: 'd'.repeat(32), assessment_kind: 'process_design_review_draft' })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="process_mapping" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('region', { name: 'Saved assessment result' })
  fireEvent.click(screen.getByText('Assessment details'))
  expect(screen.getByText('Saved process reference')).toBeInTheDocument()
  expect(screen.queryByText('Saved run reference')).not.toBeInTheDocument()
})
it.each(['missing_reference', 'run_claim'])('rejects a process feedback result with %s', async problem => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'process_mapping', assessment_kind: 'process_design_review_draft',
    run_id: problem === 'run_claim' ? saved.run_id : null, process_submission_id: problem === 'missing_reference' ? undefined : 'd'.repeat(32) })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="process_mapping" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Saved assessment result' })).not.toBeInTheDocument()
})

it('shows an original workflow approval without claiming an execution', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'workflow_design', run_id: null,
    workflow_design_submission_id: 'd'.repeat(32), assessment_kind: 'workflow_design_review_draft' })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="workflow_design" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('region', { name: 'Saved assessment result' })
  fireEvent.click(screen.getByText('Assessment details'))
  expect(screen.getByText('Saved workflow approval')).toBeInTheDocument()
  expect(screen.queryByText('Saved run reference')).not.toBeInTheDocument()
})
it.each(['missing_reference', 'run_claim'])('rejects a workflow feedback result with %s', async problem => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'workflow_design', assessment_kind: 'workflow_design_review_draft',
    run_id: problem === 'run_claim' ? saved.run_id : null, workflow_design_submission_id: problem === 'missing_reference' ? undefined : 'd'.repeat(32) })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="workflow_design" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Saved assessment result' })).not.toBeInTheDocument()
})


it('shows the original output interpretation reference without allowing a handoff', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'output_delivery', run_id: 'b'.repeat(32),
    output_review_submission_id: 'd'.repeat(32), assessment_kind: 'output_workflow_review_draft' })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="output_delivery" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('region', { name: 'Saved assessment result' })
  fireEvent.click(screen.getByText('Assessment details'))
  expect(screen.getByText('Saved output review')).toBeInTheDocument()
  expect(screen.queryByText('Saved run reference')).not.toBeInTheDocument()
})
it('rejects output feedback without its original interpretation reference', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'output_delivery', assessment_kind: 'output_workflow_review_draft', output_review_submission_id: undefined })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="output_delivery" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Saved assessment result' })).not.toBeInTheDocument()
})

it('shows the original capstone supervision reference without allowing a handoff', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'governance', run_id: 'b'.repeat(32),
    governance_review_submission_id: 'd'.repeat(32), assessment_kind: 'governance_capstone_review_draft' })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="governance" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('region', { name: 'Saved assessment result' })
  fireEvent.click(screen.getByText('Assessment details'))
  expect(screen.getByText('Saved capstone supervision review')).toBeInTheDocument()
  expect(screen.queryByText('Saved run reference')).not.toBeInTheDocument()
})
it('rejects capstone feedback without its original interpretation reference', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, module_id: 'governance', assessment_kind: 'governance_capstone_review_draft', governance_review_submission_id: undefined })
  render(<SavedAutomaticReviews enrollmentId="enrollment" moduleId="governance" initialAttemptId={saved.attempt_id} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Saved assessment result' })).not.toBeInTheDocument()
})

it('returns to the verified saved work without changing its feedback or successful checks', async () => {
  const onOpenWork = vi.fn()
  const review = { ...saved, outcomes: [...saved.outcomes, { ...saved.outcomes[0], outcome_id: 'passed', statement: 'Approved execution', verdict: 'supported' as const, revision_instruction: '' }] }
  vi.mocked(api.getAutomaticReview).mockResolvedValue(review)
  render(<SavedAutomaticReviews {...props} onOpenWork={onOpenWork} />)
  await open()
  fireEvent.click(await screen.findByRole('button', { name: 'Open saved work to review' }))
  expect(onOpenWork).toHaveBeenCalledExactlyOnceWith(review)
  expect(screen.getByText('Approved execution')).toBeInTheDocument()
  expect(screen.getByText('Compare the saved source against the assigned agency.')).toBeInTheDocument()
  expect(api.getAutomaticReview).toHaveBeenCalledOnce()
})
it('blocks navigation while the owning work has an unresolved request', async () => {
  const onOpenWork = vi.fn()
  render(<SavedAutomaticReviews {...props} onOpenWork={onOpenWork} workNavigationDisabled />)
  await open()
  const button = await screen.findByRole('button', { name: 'Open saved work to review' })
  expect(button).toBeDisabled(); fireEvent.click(button)
  expect(onOpenWork).not.toHaveBeenCalled()
})
it('rejects a malformed practical run reference before offering work navigation', async () => {
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...saved, run_id: 'untrusted-reference' })
  render(<SavedAutomaticReviews {...props} onOpenWork={vi.fn()} />)
  await open(); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Open saved work to review' })).not.toBeInTheDocument()
})
