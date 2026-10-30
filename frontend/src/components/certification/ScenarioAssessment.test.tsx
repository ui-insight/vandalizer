import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import { ScenarioAssessment } from './ScenarioAssessment'
import type { ScenarioDefinition, ScenarioSubmission } from '../../types/certification'

vi.mock('../../api/certification', () => ({ submitScenarios: vi.fn(), getScenarioSubmission: vi.fn() }))
const definition: ScenarioDefinition = { bank_id: 'test', revision: 1, bank_sha256: 'a'.repeat(64), module_id: 'ai_literacy', questions: [
  { id: 'source', prompt: 'What should you do with an unsupported claim?', choices: [{ id: 'verify', text: 'Verify it against the source' }, { id: 'accept', text: 'Accept the fluent answer' }] },
] }
const result = { passed: true, assessment_kind: 'scenario_recognition' as const, credit_awarded: false as const, checks: [{ id: 'source', name: 'Source support', passed: true, detail: 'Source verification is required.', role: 'required' as const }] }
const response: ScenarioSubmission = { attempt_id: 'b'.repeat(32), bank_sha256: definition.bank_sha256, module_id: definition.module_id, linked_to_progress: true, result }

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })

it('requires explicit choices and submission, then displays a saved result without claiming credit', async () => {
  vi.mocked(api.submitScenarios).mockResolvedValue(response)
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<ScenarioAssessment definition={definition} enrollmentId="one" onSaved={refresh} />)
  expect(screen.getByRole('button', { name: 'Submit scenario choices' })).toBeDisabled()
  fireEvent.click(screen.getByLabelText('Verify it against the source'))
  expect(api.submitScenarios).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  expect(await screen.findByText('All scenario requirements met')).toBeInTheDocument()
  expect(api.submitScenarios).toHaveBeenCalledWith('one', 'ai_literacy', expect.stringMatching(/^[a-f0-9]{32}$/), definition.bank_sha256, { source: 'verify' })
  expect(refresh).toHaveBeenCalledOnce()
  expect(screen.getByText(/No module credit or XP was awarded/)).toBeInTheDocument()
})

it('checks a lost response after remount without sending another submission', async () => {
  vi.mocked(api.submitScenarios).mockRejectedValueOnce(new Error('Lost response'))
  const first = render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Verify it against the source'))
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  await screen.findByRole('alert')
  const originalArgs = vi.mocked(api.submitScenarios).mock.calls[0]
  vi.mocked(api.getScenarioSubmission).mockResolvedValue({ uuid: originalArgs[2], enrollment_id: 'one', module_id: definition.module_id,
    bank_sha256: definition.bank_sha256, answers: originalArgs[4], result, progress_link: 'selected', read_only: true })
  expect(screen.getByLabelText('Accept the fluent answer')).toBeDisabled()
  first.unmount()
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  expect(api.submitScenarios).toHaveBeenCalledOnce()
  expect(api.getScenarioSubmission).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check saved scenario result' }))
  await screen.findByText('All scenario requirements met')
  expect(api.submitScenarios).toHaveBeenCalledOnce()
  expect(api.getScenarioSubmission).toHaveBeenCalledWith(originalArgs[2])
  expect(screen.getByLabelText('Accept the fluent answer')).not.toBeDisabled()
})

it.each(['missing', 'unlinked'] as const)('requires a separate explicit retry for a %s receipt', async state => {
  const pendingId = 'd'.repeat(32)
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, pendingId }))
  if (state === 'missing') vi.mocked(api.getScenarioSubmission).mockRejectedValue(new ApiError(404, 'Unavailable'))
  else vi.mocked(api.getScenarioSubmission).mockResolvedValue({ uuid: pendingId, enrollment_id: 'one', module_id: definition.module_id,
    bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result, progress_link: 'unlinked', read_only: true })
  vi.mocked(api.submitScenarios).mockResolvedValue({ ...response, attempt_id: pendingId })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved scenario result' }))
  const retry = await screen.findByRole('button', { name: state === 'missing' ? 'Retry original submission' : 'Finish linking saved result' })
  expect(api.submitScenarios).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Accept the fluent answer')).toBeDisabled()
  fireEvent.click(retry)
  await waitFor(() => expect(api.submitScenarios).toHaveBeenCalledWith('one', definition.module_id, pendingId, definition.bank_sha256, { source: 'verify' }))
  await waitFor(() => expect(screen.getByLabelText('Accept the fluent answer')).not.toBeDisabled())
})

it.each([401, 503])('never offers another write after an inconclusive %s check', async status => {
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, pendingId: 'd'.repeat(32) }))
  vi.mocked(api.getScenarioSubmission).mockRejectedValue(new ApiError(status, 'Unavailable'))
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved scenario result' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not check')
  expect(api.submitScenarios).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /Retry original|Finish linking/ })).not.toBeInTheDocument()
})

it.each(['uuid', 'answers', 'enrollment_id', 'module_id', 'bank_sha256'] as const)('rejects a recovered receipt with mismatched %s', async field => {
  const pendingId = 'd'.repeat(32)
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, pendingId }))
  const saved = { uuid: pendingId, enrollment_id: 'one', module_id: definition.module_id, bank_sha256: definition.bank_sha256,
    answers: { source: 'verify' }, result, progress_link: 'selected' as const, read_only: true as const }
  vi.mocked(api.getScenarioSubmission).mockResolvedValue({ ...saved, [field]: field === 'answers' ? { source: 'accept' } : 'wrong' })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved scenario result' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match')
  expect(screen.queryByText('All scenario requirements met')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Accept the fluent answer')).toBeDisabled()
  expect(api.submitScenarios).not.toHaveBeenCalled()
})

it('isolates unsent drafts by enrollment and pinned bank', () => {
  const first = render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Accept the fluent answer'))
  first.unmount()
  const second = render(<ScenarioAssessment definition={definition} enrollmentId="two" />)
  expect(screen.getByLabelText('Accept the fluent answer')).not.toBeChecked()
  second.unmount()
  render(<ScenarioAssessment definition={{ ...definition, bank_sha256: 'c'.repeat(64) }} enrollmentId="one" />)
  expect(screen.getByLabelText('Accept the fluent answer')).not.toBeChecked()
})

it('does not replace edits made while saved history loads', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof api.getScenarioSubmission>>) => void
  vi.mocked(api.getScenarioSubmission).mockReturnValue(new Promise(done => { resolve = done }))
  render(<ScenarioAssessment definition={definition} enrollmentId="one" attemptId={response.attempt_id} />)
  fireEvent.click(screen.getByLabelText('Accept the fluent answer'))
  await act(async () => resolve({ uuid: response.attempt_id, enrollment_id: 'one', module_id: definition.module_id, bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result }))
  expect(screen.getByLabelText('Accept the fluent answer')).toBeChecked()
  expect(screen.getByText('All scenario requirements met')).toBeInTheDocument()
})

it('refuses to send if the browser cannot preserve its request identity', async () => {
  const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Verify it against the source'))
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not preserve'))
  expect(api.submitScenarios).not.toHaveBeenCalled()
  spy.mockRestore()
})

it('labels an older retry without claiming it replaced newer course work', async () => {
  vi.mocked(api.submitScenarios).mockResolvedValue({ ...response, linked_to_progress: false })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Verify it against the source'))
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  expect(await screen.findByText(/A newer result remains selected/)).toBeInTheDocument()
})

it('does not leak a result from a different enrollment into the current course', async () => {
  vi.mocked(api.getScenarioSubmission).mockResolvedValue({ uuid: response.attempt_id, enrollment_id: 'other', module_id: definition.module_id, bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" attemptId={response.attempt_id} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('different course requirements')
  expect(screen.queryByText('All scenario requirements met')).not.toBeInTheDocument()
})

it.each(['superseded', 'unavailable'] as const)('shows recovered %s work without silently linking it', async progress_link => {
  const pendingId = 'd'.repeat(32)
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, pendingId }))
  vi.mocked(api.getScenarioSubmission).mockResolvedValue({ uuid: pendingId, enrollment_id: 'one', module_id: definition.module_id,
    bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result, progress_link, read_only: true })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved scenario result' }))
  await screen.findByText('All scenario requirements met')
  if (progress_link === 'superseded') {
    expect(screen.getByText(/A newer result remains selected/)).toBeInTheDocument()
    expect(screen.getByLabelText('Accept the fluent answer')).not.toBeDisabled()
  } else {
    expect(screen.getByRole('alert')).toHaveTextContent('course progress could not be confirmed')
    expect(screen.getByLabelText('Accept the fluent answer')).toBeDisabled()
  }
  expect(api.submitScenarios).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /Retry original|Finish linking/ })).not.toBeInTheDocument()
})

it('coalesces rapid read activations and holds the guard while refreshing progress', async () => {
  const pendingId = 'd'.repeat(32)
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, pendingId }))
  let resolve!: (value: Awaited<ReturnType<typeof api.getScenarioSubmission>>) => void
  vi.mocked(api.getScenarioSubmission).mockReturnValue(new Promise(done => { resolve = done }))
  let refreshed!: () => void
  const onSaved = vi.fn(() => new Promise<void>(done => { refreshed = done }))
  render(<ScenarioAssessment definition={definition} enrollmentId="one" onSaved={onSaved} />)
  const form = screen.getByRole('button', { name: 'Check saved scenario result' }).closest('form')!
  act(() => { fireEvent.submit(form); fireEvent.submit(form) })
  expect(api.getScenarioSubmission).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Checking saved result…' })).toBeDisabled()
  await act(async () => resolve({ uuid: pendingId, enrollment_id: 'one', module_id: definition.module_id,
    bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result, progress_link: 'selected', read_only: true }))
  fireEvent.submit(form)
  expect(api.submitScenarios).not.toHaveBeenCalled()
  await act(async () => refreshed())
  expect(screen.getByRole('button', { name: 'Submit scenario choices' })).not.toBeDisabled()
})

it('returns to the failed question without changing or resubmitting its saved choice', async () => {
  vi.mocked(api.submitScenarios).mockResolvedValue({ ...response, result: { ...result, passed: false, checks: [{ ...result.checks[0], passed: false }] } })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Accept the fluent answer'))
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  const review = await screen.findByRole('button', { name: 'Review scenario 1' })
  const before = sessionStorage.getItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`)
  fireEvent.click(review)
  expect(screen.getByLabelText('Accept the fluent answer')).toHaveFocus()
  expect(screen.getByLabelText('Accept the fluent answer')).toBeChecked()
  expect(sessionStorage.getItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`)).toBe(before)
  expect(api.submitScenarios).toHaveBeenCalledOnce()
  expect(screen.getByRole('group')).toHaveAccessibleName('1. ' + definition.questions[0].prompt)
  expect(screen.getByText(definition.questions[0].prompt)).toBeInTheDocument()
})

it('shows and retains the original reference when another request already saved identical choices', async () => {
  vi.mocked(api.submitScenarios).mockResolvedValue({ ...response, reused_existing: true, linked_to_progress: false })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  fireEvent.click(screen.getByLabelText('Verify it against the source'))
  fireEvent.click(screen.getByRole('button', { name: 'Submit scenario choices' }))
  expect(await screen.findByText(/These exact choices already have a saved result/)).toHaveAttribute('role', 'status')
  expect(screen.getByText(/A newer result remains selected/)).toBeInTheDocument()
  expect(screen.getByText('Submission reference: ' + response.attempt_id)).toBeInTheDocument()
  expect(JSON.parse(sessionStorage.getItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`)!)).toEqual({ answers: { source: 'verify' }, lastAttemptId: response.attempt_id })
  expect(api.submitScenarios).toHaveBeenCalledOnce()
  expect(api.getScenarioSubmission).not.toHaveBeenCalled()
})

it('retains the earlier-result warning when reopening an original deduplicated reference', async () => {
  sessionStorage.setItem(`certification-scenarios:one:${definition.module_id}:${definition.bank_sha256}`, JSON.stringify({ answers: { source: 'verify' }, lastAttemptId: response.attempt_id }))
  vi.mocked(api.getScenarioSubmission).mockResolvedValue({ uuid: response.attempt_id, enrollment_id: 'one', module_id: definition.module_id,
    bank_sha256: definition.bank_sha256, answers: { source: 'verify' }, result, progress_link: 'superseded', read_only: true })
  render(<ScenarioAssessment definition={definition} enrollmentId="one" />)
  expect(await screen.findByText(/A newer result remains selected/)).toBeInTheDocument()
  expect(api.getScenarioSubmission).toHaveBeenCalledWith(response.attempt_id)
  expect(api.submitScenarios).not.toHaveBeenCalled()
})
