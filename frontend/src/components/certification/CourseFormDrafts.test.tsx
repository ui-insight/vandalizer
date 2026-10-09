import type { ContextType, ReactNode } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import validationJson from './__fixtures__/validation-repair-http.json?raw'
import governanceJson from './__fixtures__/governance-http.json?raw'
import { AuthContext } from '../../contexts/AuthContext'
import { ValidationExpectationsForm, ValidationInterpretationForm } from './ValidationForms'
import { GovernanceMemoForm, GovernanceReviewForm, GovernanceCorrectionForm, GovernanceFindingForm, GovernanceReleaseForm } from './GovernanceForms'
import type { ValidationRun } from '../../types/validationSuite'
import type { GovernanceReview } from '../../types/governanceAssessment'
import { courseDraftKey } from '../../hooks/useCourseDraft'

const capture = (JSON.parse(validationJson) as { original: ValidationRun }).original.input_snapshot
const review = (JSON.parse(governanceJson) as { review: GovernanceReview }).review
const run = review.handoff.release.memo.run
const send = vi.fn()
function auth(child: ReactNode, userId = 'draft-learner') {
  return <AuthContext.Provider value={{ user: { user_id: userId } } as NonNullable<ContextType<typeof AuthContext>>}>{child}</AuthContext.Provider>
}
function form(value = capture, user = 'draft-learner', locked = false) {
  return auth(<ValidationExpectationsForm capture={value} locked={locked} send={send} />, user)
}
const key = courseDraftKey('draft-learner', ['validation-expectations', capture.enrollment_id, capture.manifest_sha256, capture.uuid, capture.input_snapshot_sha256, capture.case.case_sha256])
beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); send.mockReset() })

it('restores authored expectations and source quotes after unmount without submitting', () => {
  let view = render(form())
  fireEvent.change(screen.getAllByLabelText('Expected value')[0], { target: { value: 'Original expected value' } })
  fireEvent.change(screen.getAllByLabelText('Exact source quote')[0], { target: { value: 'Original exact source quote' } })
  fireEvent.change(screen.getAllByLabelText('Source page')[0], { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText(capture.case.questions.find(q => q.id === 'suite_design')!.prompt), { target: { value: 'Original coverage explanation' } })
  view.unmount()
  view = render(form())
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('Original expected value')
  expect(screen.getAllByLabelText('Exact source quote')[0]).toHaveValue('Original exact source quote')
  expect(screen.getAllByLabelText('Source page')[0]).toHaveValue(2)
  expect(screen.getByLabelText(capture.case.questions.find(q => q.id === 'suite_design')!.prompt)).toHaveValue('Original coverage explanation')
  expect(screen.getByRole('status')).toHaveTextContent('Draft kept in this browser tab')
  expect(send).not.toHaveBeenCalled()
  fireEvent.submit(screen.getByRole('form', { name: 'Save representative test expectations' }))
  expect(send).toHaveBeenCalledTimes(1)
  expect(send.mock.calls[0][0].body.expectations[0]).toMatchObject({ expected_value: 'Original expected value', source_references: [{ page: 2, quote: 'Original exact source quote' }] })
  view.rerender(form(capture, 'draft-learner', true))
  view.unmount()
  render(form()) // Unconfirmed submission does not erase the original authored draft.
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('Original expected value')
  expect(send).toHaveBeenCalledTimes(1)
})

it.each(['user', 'enrollment', 'manifest', 'capture', 'input', 'case'])('isolates drafts when %s changes and restores the original on return', binding => {
  const view = render(form())
  fireEvent.change(screen.getAllByLabelText('Expected value')[0], { target: { value: 'Original private answer' } })
  const changed = structuredClone(capture)
  if (binding === 'enrollment') changed.enrollment_id += '-different'
  if (binding === 'manifest') changed.manifest_sha256 = 'f'.repeat(64)
  if (binding === 'capture') changed.uuid += '-different'
  if (binding === 'input') changed.input_snapshot_sha256 = 'f'.repeat(64)
  if (binding === 'case') changed.case.case_sha256 = 'f'.repeat(64)
  view.rerender(form(changed, binding === 'user' ? 'another-learner' : 'draft-learner'))
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('')
  fireEvent.change(screen.getAllByLabelText('Expected value')[0], { target: { value: 'New course answer' } })
  view.rerender(form())
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('Original private answer')
  expect(send).not.toHaveBeenCalled()
})

it('rejects stored expectations for different source fields without submitting or replacing the record', () => {
  const raw = JSON.stringify({ schema: 1, value: { expectations: [{ source_id: 'forged', field: 'forged' }], design: 'forged' } })
  sessionStorage.setItem(key, raw)
  render(form())
  expect(screen.getByRole('status')).toHaveTextContent('could not restore a valid draft')
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('')
  expect(sessionStorage.getItem(key)).toBe(raw)
  expect(send).not.toHaveBeenCalled()
})

it('keeps typed edits and explains unavailable storage', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota or permission failure') })
  render(form())
  fireEvent.change(screen.getAllByLabelText('Expected value')[0], { target: { value: 'Retained in this form' } })
  expect(screen.getAllByLabelText('Expected value')[0]).toHaveValue('Retained in this form')
  expect(screen.getByRole('status')).toHaveTextContent('Keep this form open')
  expect(send).not.toHaveBeenCalled()
})

it('preserves memo drafts without releasing or approving the memo', () => {
  const node = auth(<GovernanceMemoForm run={run} locked={false} send={send} />)
  const view = render(node)
  for (const label of ['Intended use', 'Supported inputs and source scope', 'Known limitations', 'Change and review route · distinguish real-world review roles from certification staff']) {
    fireEvent.change(screen.getByLabelText(label), { target: { value: `Draft: ${label}` } })
  }
  view.unmount()
  render(node)
  expect(screen.getByLabelText('Intended use')).toHaveValue('Draft: Intended use')
  expect(screen.getByLabelText('Known limitations')).toHaveValue('Draft: Known limitations')
  expect(send).not.toHaveBeenCalled()
})

it('separates a revised supervision draft from its original submission and handoff', () => {
  const node = (previous?: GovernanceReview) => auth(<GovernanceReviewForm handoff={review.handoff} previous={previous} locked={false} send={send} />)
  const view = render(node(review))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My unfinished revised explanation' } })
  view.rerender(node())
  expect(screen.getByRole('textbox')).toHaveValue('')
  view.rerender(node(review))
  expect(screen.getByRole('textbox')).toHaveValue('My unfinished revised explanation')
  expect(review.submission.final_supervision).not.toBe('My unfinished revised explanation')
  expect(send).not.toHaveBeenCalled()
})


it('restores a scope correction only for its original captured sources', () => {
  const captured = run.source_finding!.run.input_snapshot
  const node = (value = captured) => auth(<GovernanceCorrectionForm capture={value} locked={false} send={send} />)
  let view = render(node())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My original correction rejecting the broad proposed scope.' } })
  view.unmount()
  view = render(node())
  expect(screen.getByRole('textbox')).toHaveValue('My original correction rejecting the broad proposed scope.')
  view.rerender(node({ ...captured, input_snapshot_sha256: 'e'.repeat(64) }))
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(send).not.toHaveBeenCalled()
})

it('keeps the original finding and both source references through navigation', () => {
  const original = run.source_finding!.run
  const node = (value = original) => auth(<GovernanceFindingForm run={value} locked={false} send={send} />)
  let view = render(node())
  fireEvent.change(screen.getByLabelText('Actual unsupported Funds Obligated to Date value'), { target: { value: '600000' } })
  fireEvent.change(screen.getByLabelText('Exact award notice page quote'), { target: { value: 'My original award notice quote.' } })
  fireEvent.change(screen.getByLabelText('Award notice page'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('Exact issued amendment page quote'), { target: { value: 'My original amendment quote.' } })
  fireEvent.change(screen.getByLabelText('Explain the actual mismatch and the instruction change you will test'), { target: { value: 'My original explanation of the actual mismatch and intended repair.' } })
  view.unmount()
  view = render(node())
  expect(screen.getByLabelText('Actual unsupported Funds Obligated to Date value')).toHaveValue('600000')
  expect(screen.getByLabelText('Exact award notice page quote')).toHaveValue('My original award notice quote.')
  expect(screen.getByLabelText('Award notice page')).toHaveValue(2)
  expect(screen.getByLabelText('Exact issued amendment page quote')).toHaveValue('My original amendment quote.')
  expect(send).not.toHaveBeenCalled()
  view.rerender(node({ ...original, result_sha256: 'e'.repeat(64) }))
  expect(screen.getByLabelText('Actual unsupported Funds Obligated to Date value')).toHaveValue('')
  expect(screen.getByLabelText('Award notice page')).toHaveValue(1)
})

it('restores a release draft without saving or handing off and clears its acknowledgement for different bytes', () => {
  const memo = review.handoff.release.memo
  const node = (value = memo) => auth(<GovernanceReleaseForm memo={value} locked={false} send={send} />)
  let view = render(node())
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My original release rationale for this exact private memo.' } })
  view.unmount()
  view = render(node())
  expect(screen.getByRole('checkbox')).toBeChecked()
  expect(screen.getByRole('combobox')).toHaveValue('approve')
  expect(screen.getByRole('textbox')).toHaveValue('My original release rationale for this exact private memo.')
  expect(send).not.toHaveBeenCalled()
  view.rerender(node({ ...memo, file: { ...memo.file, sha256: 'f'.repeat(64) } }))
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  expect(screen.getByRole('combobox')).toHaveValue('hold')
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(send).not.toHaveBeenCalled()
})


it('restores repair interpretation for its original retest and revision lineage', () => {
  const original = (JSON.parse(validationJson) as { original: ValidationRun }).original
  const retest: ValidationRun = { ...original, run_id: 'f'.repeat(32), phase: 'retest', original_run: original }
  const node = (previous: string | null = null, initialAnswer = '', value = retest) => auth(<ValidationInterpretationForm run={value} previous={previous} initialAnswer={initialAnswer} locked={false} send={send} />)
  let view = render(node())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My original analysis of the complete retest and its remaining limits.' } })
  view.unmount()
  view = render(node())
  expect(screen.getByRole('textbox')).toHaveValue('My original analysis of the complete retest and its remaining limits.')
  view.rerender(node('e'.repeat(32), 'The earlier saved interpretation.'))
  expect(screen.getByRole('textbox')).toHaveValue('The earlier saved interpretation.')
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'My unsubmitted revision of that earlier explanation.' } })
  view.rerender(node())
  expect(screen.getByRole('textbox')).toHaveValue('My original analysis of the complete retest and its remaining limits.')
  view.rerender(node(null, '', { ...retest, result_sha256: 'a'.repeat(64) }))
  expect(screen.getByRole('textbox')).toHaveValue('')
  expect(send).not.toHaveBeenCalled()
})
