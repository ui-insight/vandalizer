import fixtureJson from './__fixtures__/governance-http.json?raw'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/governanceAssessment'
import { ApiError } from '../../api/client'
import type { GovernanceList, GovernanceRequest, GovernanceReview, GovernanceRun, GovernanceView } from '../../types/governanceAssessment'
import { GovernanceAssessment } from './GovernanceAssessment'
import { GovernanceReleaseForm } from './GovernanceForms'
import { useGovernanceRequest } from './useGovernanceRequest'
import { validGovernanceRequest, verifyGovernanceResponse, verifyGovernanceView } from './governanceAssessmentState'
vi.mock('../../api/governanceAssessment', async importOriginal => ({ ...await importOriginal<typeof import('../../api/governanceAssessment')>(), getGovernanceWork: vi.fn(), getGovernanceRecord: vi.fn(), saveGovernanceWork: vi.fn(), downloadGovernanceFile: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved feedback</p> }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: () => <p>Explicit automatic assessment</p> }))
// Real synthetic HTTP responses from the disposable-MongoDB journey. These are
// fixture actor/model outputs, not live learner or calibration evidence.
const fixture = JSON.parse(fixtureJson) as { listing: GovernanceList; review: GovernanceReview; prepared_runs: GovernanceRun[] }
const listing = fixture.listing, definition = listing.case, review = fixture.review
const handoff = review.handoff, release = handoff.release, memo = release.memo, repaired = memo.run, finding = repaired.source_finding!, original = finding.run, correction = original.scope_correction, capture = original.input_snapshot
const views: GovernanceView[] = [
  { kind: 'capture', value: capture }, { kind: 'correction', value: correction }, { kind: 'run', value: original }, { kind: 'finding', value: finding },
  { kind: 'capture', value: repaired.input_snapshot }, { kind: 'run', value: repaired }, { kind: 'memo', value: memo }, { kind: 'release', value: release },
  { kind: 'handoff', value: handoff.previous_failed_receipt! }, { kind: 'handoff', value: handoff }, { kind: 'review', value: review },
  { kind: 'scope', value: { ...original.scope_decision!, record_sha256: original.scope_decision_sha256! } },
]
const key = `certification-governance-request:${listing.enrollment_id}:${definition.case_sha256}`
const request: GovernanceRequest = { action: 'capture', body: { request_id: capture.uuid, artifact_id: capture.artifact_id, case_sha256: definition.case_sha256, consent: 'capture_governance_extraction_and_complete_sources' } }
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getGovernanceWork).mockResolvedValue(clone(listing))
  vi.mocked(api.getGovernanceRecord).mockImplementation(async (_e, kind, ref) => {
    const value = views.find(v => v.kind === kind && (v.kind === 'run' ? v.value.run_id : v.value.uuid) === ref)
    if (!value) throw new ApiError(404, 'No original record')
    return clone(value)
  })
})
it('accepts the complete actual HTTP chain and both separately prepared plans', () => {
  for (const view of views) expect(() => verifyGovernanceView(view, listing)).not.toThrow()
  for (const run of fixture.prepared_runs) expect(() => verifyGovernanceView({ kind: 'run', value: run }, listing)).not.toThrow()
})
it('opens preserved full capstone history without write forms or automatic actions', async () => {
  render(<GovernanceAssessment enrollmentId={listing.enrollment_id} definition={definition} historyOnly />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open supervision interpretation 1' }))
  await screen.findByRole('region', { name: 'Opened capstone evidence' })
  expect(screen.getByText(review.submission.final_supervision)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Download exact accountable memo JSON' })).toBeInTheDocument()
  expect(screen.queryByRole('form', { name: 'Capture your capstone extraction' })).not.toBeInTheDocument()
  expect(screen.queryByText('Explicit automatic assessment')).not.toBeInTheDocument()
  expect(api.saveGovernanceWork).not.toHaveBeenCalled()
})
it('replaces opened evidence after a saved release and handoff without retaining old download controls', async () => {
  const fresh = clone(listing)
  fresh.records.handoff.items = []
  vi.mocked(api.getGovernanceWork).mockResolvedValue(fresh)
  vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce(release.uuid as ReturnType<Crypto['randomUUID']>)
    .mockReturnValueOnce(handoff.previous_failed_receipt!.uuid as ReturnType<Crypto['randomUUID']>)
  vi.mocked(api.saveGovernanceWork).mockResolvedValueOnce({ kind: 'release', value: release })
    .mockResolvedValueOnce({ kind: 'handoff', value: handoff.previous_failed_receipt! })
  render(<GovernanceAssessment enrollmentId={listing.enrollment_id} definition={definition} />)
  fireEvent.change(await screen.findByRole('combobox', { name: 'Saved capstone record type' }), { target: { value: 'memo' } })
  fireEvent.change(screen.getByRole('textbox', { name: 'Saved capstone reference' }), { target: { value: memo.uuid } })
  fireEvent.click(screen.getByRole('button', { name: 'Open saved capstone reference' }))
  fireEvent.click(await screen.findByRole('checkbox', { name: 'I opened and inspected this exact downloaded memo.' }))
  fireEvent.change(screen.getByRole('combobox', { name: 'Memo release choice' }), { target: { value: 'approve' } })
  fireEvent.change(screen.getByRole('textbox', { name: definition.questions.find(q => q.id === 'release_review')!.prompt }), { target: { value: release.submission.reason } })
  fireEvent.click(screen.getByRole('button', { name: 'Save my exact memo release choice' }))
  await screen.findByRole('button', { name: 'Open this memo to reconsider release' })
  expect(screen.getAllByRole('button', { name: 'Download exact accountable memo JSON' })).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Attempt approved private memo handoff' }))
  await screen.findByRole('heading', { name: 'Disclosed training rejection · no destination write' })
  expect(screen.getAllByRole('button', { name: 'Download exact accountable memo JSON' })).toHaveLength(1)
  expect(screen.queryByRole('heading', { name: 'Memo release or hold' })).not.toBeInTheDocument()
})
it('saves pending details before POST and resolves a lost reply through GET only', async () => {
  const onSaved = vi.fn()
  vi.mocked(api.saveGovernanceWork).mockImplementation(async () => { expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(request); throw new Error('Lost response') })
  const hook = renderHook(() => useGovernanceRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.check() })
  expect(api.saveGovernanceWork).toHaveBeenCalledOnce()
  expect(api.getGovernanceRecord).toHaveBeenCalledWith(listing.enrollment_id, 'capture', capture.uuid)
  expect(onSaved).toHaveBeenCalledWith({ kind: 'capture', value: capture })
  expect(sessionStorage.getItem(key)).toBeNull()
})
it('restores the same request on remount and requires explicit finish when missing', async () => {
  sessionStorage.setItem(key, JSON.stringify(request))
  vi.mocked(api.getGovernanceRecord).mockRejectedValue(new ApiError(404, 'Missing'))
  vi.mocked(api.saveGovernanceWork).mockResolvedValue({ kind: 'capture', value: capture })
  const hook = renderHook(() => useGovernanceRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.pending).toEqual(request))
  await act(async () => { await hook.result.current.check() })
  expect(api.saveGovernanceWork).not.toHaveBeenCalled()
  expect(hook.result.current.canFinish).toBe(true)
  await act(async () => { await hook.result.current.finish() })
  expect(api.saveGovernanceWork).toHaveBeenCalledWith(listing.enrollment_id, request)
})
it('blocks new work when pending storage is malformed', async () => {
  sessionStorage.setItem(key, '{broken')
  const hook = renderHook(() => useGovernanceRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.blocked).toBe(true))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveGovernanceWork).not.toHaveBeenCalled()
})
it('does not dispatch when the original request cannot be stored', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage full') })
  const hook = renderHook(() => useGovernanceRequest(listing, vi.fn()))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveGovernanceWork).not.toHaveBeenCalled()
  expect(hook.result.current.error).toMatch(/no request was sent/)
})
it('keeps a mismatched response pending and prevents replacement work', async () => {
  vi.mocked(api.saveGovernanceWork).mockResolvedValue({ kind: 'capture', value: { ...capture, enrollment_id: 'foreign' } })
  const onSaved = vi.fn(), hook = renderHook(() => useGovernanceRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.send(request) })
  expect(onSaved).not.toHaveBeenCalled(); expect(api.saveGovernanceWork).toHaveBeenCalledOnce()
})
it.each(['case', 'source', 'revision', 'authority'])('rejects changed %s in source capture', change => {
  const altered = clone(capture)
  if (change === 'case') altered.case.case_sha256 = '0'.repeat(64)
  if (change === 'source') altered.documents[1].source_sha256 = '0'.repeat(64)
  if (change === 'revision') altered.artifact.uuid = '0'.repeat(32)
  if (change === 'authority') Object.assign(altered, { credit_awarded: true })
  expect(() => verifyGovernanceResponse({ kind: 'capture', value: altered }, listing, request)).toThrow()
})
it.each(['original', 'models', 'revision', 'funding', 'receipt'])('rejects a changed %s repair chain', change => {
  const altered = clone(repaired)
  if (change === 'original') altered.original_run_sha256 = '0'.repeat(64)
  if (change === 'models') altered.model_names = ['unapproved-model']
  if (change === 'revision') altered.input_snapshot.artifact_id = '0'.repeat(32)
  if (change === 'funding') altered.changed_fields = ['Award ID']
  if (change === 'receipt') altered.extraction_events[1].receipt.result = { invented: true }
  expect(() => verifyGovernanceView({ kind: 'run', value: altered }, listing)).toThrow()
})
it.each(['copy', 'approval', 'failure', 'external'])('rejects a changed %s private handoff', change => {
  const altered = clone(handoff)
  if (change === 'copy') altered.destination_copy!.sha256 = '0'.repeat(64)
  if (change === 'approval') altered.release.submission.choice = 'hold'
  if (change === 'failure') altered.previous_failed_receipt = null
  if (change === 'external') Object.assign(altered, { external_delivery: true })
  expect(() => verifyGovernanceView({ kind: 'handoff', value: altered }, listing)).toThrow()
})
it('requires explicit opening acknowledgement for approve while hold remains available', () => {
  const send = vi.fn()
  render(<GovernanceReleaseForm memo={memo} locked={false} send={send} />)
  const submit = screen.getByRole('button', { name: 'Save my exact memo release choice' })
  expect(submit).toBeEnabled()
  fireEvent.change(screen.getByLabelText('Memo release choice'), { target: { value: 'approve' } })
  expect(submit).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox'))
  expect(submit).toBeEnabled()
  expect(send).not.toHaveBeenCalled()
})
it('rejects disabled authority, guessed sources, blank explanations and unbound repair requests', () => {
  expect(validGovernanceRequest({ action: 'correction', body: { ...correction.submission, ongoing_automation: 'enable' } } as unknown as GovernanceRequest, definition)).toBe(false)
  expect(validGovernanceRequest({ action: 'finding', body: { ...finding.submission, explanation: ' '.repeat(40) } }, definition)).toBe(false)
  expect(validGovernanceRequest({ action: 'prepare', body: { request_id: 'e'.repeat(32), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256,
    case_sha256: definition.case_sha256, scope_correction_id: correction.uuid, scope_correction_sha256: correction.record_sha256, source_finding_id: finding.uuid,
    source_finding_sha256: null, consent: 'prepare_repaired_bounded_capstone_extraction' } }, definition)).toBe(false)
})
it('reads an unstarted execution without sending and finishes only the original approved request', async () => {
  const prepared = clone(fixture.prepared_runs[0])
  Object.assign(prepared, { scope_decision: original.scope_decision, scope_decision_id: original.scope_decision_id, scope_decision_sha256: original.scope_decision_sha256, can_execute: true })
  const execute: GovernanceRequest = { action: 'execute', body: { run_id: prepared.run_id, plan_sha256: prepared.plan_sha256, scope_decision_id: original.scope_decision_id!, scope_decision_sha256: original.scope_decision_sha256!, consent: 'execute_approved_bounded_capstone_extraction' } }
  sessionStorage.setItem(key, JSON.stringify(execute))
  vi.mocked(api.getGovernanceRecord).mockResolvedValue({ kind: 'run', value: prepared })
  vi.mocked(api.saveGovernanceWork).mockResolvedValue({ kind: 'run', value: original })
  const hook = renderHook(() => useGovernanceRequest(listing, vi.fn()))
  await act(async () => { await hook.result.current.check() })
  expect(hook.result.current.canFinish).toBe(true); expect(api.saveGovernanceWork).not.toHaveBeenCalled()
  await act(async () => { await hook.result.current.finish() })
  expect(api.saveGovernanceWork).toHaveBeenCalledWith(listing.enrollment_id, execute)
})

it('opens the exact current extraction from its saved repair finding without capturing or replacing evidence', async () => {
  render(<GovernanceAssessment enrollmentId={listing.enrollment_id} definition={definition} />)
  fireEvent.change(await screen.findByLabelText('Saved capstone record type'), { target: { value: 'finding' } })
  fireEvent.change(screen.getByLabelText('Saved capstone reference'), { target: { value: finding.uuid } })
  fireEvent.click(screen.getByRole('button', { name: 'Open saved capstone reference' }))
  await screen.findByRole('heading', { name: 'Repair the same extraction, then capture it' })
  const link = screen.getByRole('link', { name: 'Open selected extraction in a new tab' })
  expect(new URL(link.getAttribute('href')!, 'http://localhost').searchParams.get('extraction')).toBe(finding.run.input_snapshot.artifact_id)
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(api.saveGovernanceWork).not.toHaveBeenCalled()
})

it('announces a sent request separately from checking its preserved state after response loss', async () => {
  let reject!: (error: Error) => void
  vi.mocked(api.saveGovernanceWork).mockReturnValue(new Promise((_resolve, fail) => { reject = fail }))
  const assignment = clone(listing)
  const hook = renderHook(() => useGovernanceRequest(assignment, vi.fn()))
  let sending!: Promise<void>
  act(() => { sending = hook.result.current.send(request) })
  expect(hook.result.current.phase).toBe('sending')
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { reject(new ApiError(503, 'Synthetic lost response')); await sending })
  expect(hook.result.current.phase).toBeNull()
  vi.mocked(api.getGovernanceRecord).mockReturnValue(new Promise((_resolve, fail) => { reject = fail }))
  let checking!: Promise<void>
  act(() => { checking = hook.result.current.check() })
  expect(hook.result.current.phase).toBe('checking')
  expect(api.saveGovernanceWork).toHaveBeenCalledOnce()
  await act(async () => { reject(new ApiError(503, 'Synthetic unavailable read')); await checking })
  expect(hook.result.current.phase).toBeNull()
  expect(hook.result.current.pending).toEqual(request)
  expect(hook.result.current.canFinish).toBe(false)
})
