import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/batchAssessment'
import { ApiError } from '../../api/client'
import type { BatchCapture, BatchCase, BatchList, BatchRequest, BatchRun, BatchItemResult } from '../../types/batchAssessment'
import { BatchAssessment } from './BatchAssessment'
import { BatchInterpretationForm } from './BatchForms'
import { useBatchRequest } from './useBatchRequest'
import { validBatchRequest, verifyBatchResponse, verifyBatchRun } from './batchAssessmentState'
vi.mock('../../api/batchAssessment', () => ({ getBatchWork: vi.fn(), getBatchCapture: vi.fn(), getBatchAssessment: vi.fn(), getBatchRun: vi.fn(), getBatchScope: vi.fn(), getBatchReview: vi.fn(), saveBatchWork: vi.fn(), getBatchSource: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved feedback</p> }))
const definition: BatchCase = { id: 'case', revision: 1, module_id: 'batch_processing', case_sha256: 'a'.repeat(64),
  provenance: 'authored_batch_assignment_not_pilot_coverage_or_recovery_evidence', notice: 'Draft feedback only', task: 'Check a bounded pilot and recover an exact failed batch item.',
  instructions: ['Inspect all sources.'], exclusions: ['No staff review.'], pilot_limitations: 'One shared template cannot establish wider reliability.',
  pilot_source_ids: ['proposal_1', 'proposal_3'], controlled_failure_source_id: 'proposal_2',
  consolidated_draft: [1, 2, 3].flatMap(i => ['PI Name', 'Institution', 'Total Budget', 'Research Area', 'Sponsoring Agency'].map(field => ({ source_id: `proposal_${i}` as 'proposal_1' | 'proposal_2' | 'proposal_3', field, value: i === 3 && field === 'Research Area' ? 'Biological Sciences' : `${field} ${i}` }))),
  fields: ['PI Name', 'Institution', 'Total Budget', 'Research Area', 'Sponsoring Agency'].map(title => ({ title, meaning: title, comparison: 'exact_text' })),
  sources: [1, 2, 3].map(i => ({ id: `proposal_${i}` as 'proposal_1' | 'proposal_2' | 'proposal_3', filename: `proposal-${i}.pdf`, sha256: String(i).repeat(64), coverage: 'Assigned source' })),
  questions: [{ id: 'pilot_choice', phase: 'before_pilot', prompt: 'Explain pilot scope.' }, { id: 'scale_choice', phase: 'before_batch', prompt: 'Explain source quality and resource tradeoffs.' },
    { id: 'recovery_choice', phase: 'before_retry', prompt: 'Explain the exact failure and preserved successes.' }, { id: 'batch_review', phase: 'after_recovery', prompt: 'Reconcile actual results and limitations.' }] }
const identity = { enrollment_id: 'enrollment', module_id: 'batch_processing' as const, course_version: 'draft', manifest_sha256: 'd'.repeat(64) }
// The editor, chat and library create extraction sets with hyphenated uuid4 strings.
const artifact = '2a6f3c1e-8b4d-4e2f-9a1b-3c5d7e9f0a12', snapshotId = 'f'.repeat(32)
const assignedIds = ['1', '2', '3'].map(c => c.repeat(32)), wrongId = 'course_asset:nsf-proposal-alpine-ecology.pdf'
const request: BatchRequest = { action: 'capture', body: { request_id: snapshotId, artifact_id: artifact, case_sha256: definition.case_sha256, selected_source_ids: assignedIds, consent: 'capture_batch_extraction_and_complete_sources' } }
const key = `certification-batch-request:enrollment:${definition.case_sha256}`
const capture: BatchCapture = { ...identity, uuid: snapshotId, case: definition, input_snapshot_sha256: '1'.repeat(64), artifact_id: artifact, artifact_sha256: '2'.repeat(64), captured_at: '2026-10-07', execution_authorized: false, credit_awarded: false,
  artifact: { uuid: artifact, title: 'Original extraction', fields: definition.fields.map((f, i) => ({ id: String(i), title: f.title, searchphrase: f.meaning, is_optional: i === 2, enum_values: [] })) },
  documents: definition.sources.map((s, i) => ({ source_id: s.id, document_id: String(i + 1).repeat(32), assigned_filename: s.filename, source_sha256: s.sha256, pages: ['Original source page'], text: 'Original source page' })),
  scope_review: { proposed_source_ids: [assignedIds[0], wrongId, ...assignedIds.slice(1)], selected_source_ids: assignedIds, removed_source_ids: [wrongId], removed_filename: 'nsf-proposal-alpine-ecology.pdf', removed_sha256: '9'.repeat(64) } }
const listing: BatchList = { ...identity, case: definition, can_submit: true, read_only_reason: null, extractions: [{ artifact_id: artifact, title: 'Original extraction' }], older_extractions_available: false,
  assigned_sources: [], proposed_scope: [assignedIds[0], wrongId, ...assignedIds.slice(1)].map(document_id => ({ document_id, title: document_id === wrongId ? 'nsf-proposal-alpine-ecology.pdf' : `proposal-${document_id[0]}.pdf`, preview: 'Principal Investigator and budget' })),
  captures: [{ input_snapshot_id: snapshotId, extraction_name: 'Original extraction', captured_at: '2026-10-07' }], older_captures_available: false, runs: [], older_runs_available: false, submissions: [], older_submissions_available: false }
beforeEach(() => { vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear(); vi.mocked(api.getBatchWork).mockResolvedValue(structuredClone(listing)); vi.mocked(api.getBatchCapture).mockResolvedValue(structuredClone(capture)) })
it('opens original sources in history without capture, expectation forms or mutations', async () => {
  render(<BatchAssessment enrollmentId="enrollment" definition={definition} historyOnly />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open capture 1: Original extraction' }))
  await screen.findByRole('button', { name: 'Download original PROPOSAL_3 PDF' })
  expect(screen.getByText(/Removed from the proposed batch before capture/)).toHaveTextContent('nsf-proposal-alpine-ecology.pdf')
  expect(screen.queryByRole('form', { name: 'Capture batch extraction' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Prepare two-document pilot' })).not.toBeInTheDocument()
  expect(api.saveBatchWork).not.toHaveBeenCalled()
})
it('persists before POST and recovers a lost capture reply with GET only', async () => {
  const onSaved = vi.fn()
  vi.mocked(api.saveBatchWork).mockImplementation(async () => { expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(request); throw new Error('Lost reply') })
  const hook = renderHook(() => useBatchRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.check() })
  expect(api.saveBatchWork).toHaveBeenCalledOnce()
  expect(api.getBatchCapture).toHaveBeenCalledWith('enrollment', snapshotId)
  expect(onSaved).toHaveBeenCalledWith(capture, 'capture')
  expect(sessionStorage.getItem(key)).toBeNull()
})
it('restores pending identity after remount and requires explicit finish for missing saved work', async () => {
  sessionStorage.setItem(key, JSON.stringify(request))
  vi.mocked(api.getBatchCapture).mockRejectedValue(new ApiError(404, 'Missing'))
  vi.mocked(api.saveBatchWork).mockResolvedValue(capture)
  const hook = renderHook(() => useBatchRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.pending).toEqual(request))
  await act(async () => { await hook.result.current.check() })
  expect(hook.result.current.canFinish).toBe(true)
  expect(api.saveBatchWork).not.toHaveBeenCalled()
  await act(async () => { await hook.result.current.finish() })
  expect(api.saveBatchWork).toHaveBeenCalledWith('enrollment', request)
})
it('blocks new writes when pending storage is malformed', async () => {
  sessionStorage.setItem(key, '{broken')
  const hook = renderHook(() => useBatchRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.blocked).toBe(true))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveBatchWork).not.toHaveBeenCalled()
})
it('does not send when the original request cannot be preserved', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage full') })
  const hook = renderHook(() => useBatchRequest(listing, vi.fn()))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveBatchWork).not.toHaveBeenCalled()
  expect(hook.result.current.error).toMatch(/no request was sent/)
})
it('leaves an ambiguous mismatched response pending and rejects another write', async () => {
  vi.mocked(api.saveBatchWork).mockResolvedValue({ ...capture, enrollment_id: 'foreign' })
  const onSaved = vi.fn(), hook = renderHook(() => useBatchRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.send({ ...request, body: { ...request.body, request_id: '9'.repeat(32) } }) })
  expect(onSaved).not.toHaveBeenCalled(); expect(api.saveBatchWork).toHaveBeenCalledOnce()
})
it.each(['case', 'source', 'artifact', 'credit'])('rejects changed %s identity in capture evidence', change => {
  const wrong = structuredClone(capture)
  if (change === 'case') wrong.case.case_sha256 = '9'.repeat(64)
  if (change === 'source') wrong.documents[1].source_sha256 = '9'.repeat(64)
  if (change === 'artifact') wrong.artifact.uuid = '9'.repeat(32)
  if (change === 'credit') Object.assign(wrong, { credit_awarded: true })
  expect(() => verifyBatchResponse(wrong, listing, request)).toThrow()
})
it('rejects saved requests missing the case or carrying a different course assignment', () => {
  expect(validBatchRequest({ ...request, body: { ...request.body, case_sha256: undefined } } as unknown as BatchRequest, definition)).toBe(false)
  expect(validBatchRequest({ ...request, body: { ...request.body, case_sha256: '0'.repeat(64) } }, definition)).toBe(false)
})
function completed(phase: BatchRun['phase'], parent: BatchRun | null = null): BatchRun {
  const runId = ({ pilot: '4', batch: '5', retry: '6' }[phase]).repeat(32), batchId = phase === 'retry' ? parent!.run_id : runId
  const sources = phase === 'pilot' ? definition.pilot_source_ids : phase === 'batch' ? definition.sources.map(s => s.id) : ['proposal_2' as const]
  const items: BatchItemResult[] = sources.map(source => ({ source_id: source, document_id: capture.documents.find(d => d.source_id === source)!.document_id,
    item_id: source.slice(-1).repeat(32), batch_id: batchId, run_id: runId, attempt_kind: phase,
    status: phase === 'batch' && source === 'proposal_2' ? 'failed' : 'completed', reason: phase === 'batch' && source === 'proposal_2' ? 'controlled_training_rejection_before_dispatch' : null,
    extraction_started: !(phase === 'batch' && source === 'proposal_2'), started_at: '2026-10-07T12:00:00Z', finished_at: '2026-10-07T12:00:01Z', elapsed_ms: 1000, usage: null, cost: null, entities: [], external_effects: false }))
  return { ...identity, run_id: runId, run_sha256: runId.repeat(2), state: 'completed', phase, batch_id: batchId, source_ids: sources,
    failed_source_id: phase === 'retry' ? 'proposal_2' : null, plan_sha256: '7'.repeat(64), case_sha256: definition.case_sha256, input_snapshot: capture, input_snapshot_id: capture.uuid,
    model_names: ['synthetic-model'], prepared_at: '2026-10-07', parent_run: parent, previous_retry: null, scope_decision_id: null, scope_decision_sha256: null, scope_decision: null,
    authorization_sha256: '8'.repeat(64), result_sha256: '9'.repeat(64), item_events_sha256: 'a'.repeat(64),
    item_events: items.flatMap((item, i) => [{ receipt_sha256: 'b'.repeat(64), receipt: { kind: 'item_started' as const, item_index: i } }, { receipt_sha256: 'c'.repeat(64), receipt: { kind: 'item_completed' as const, item_index: i, result: item } }]),
    result: { status: 'completed', item_results: items, checks: { terminal_coverage_complete: true, all_items_completed: phase !== 'batch', all_values_complete: phase !== 'batch',
      all_values_source_supported: phase !== 'batch', source_ids: sources, elapsed_ms: 1000, usage: null, cost: null,
      items: items.map(item => ({ ...item, receipt_sha256: 'd'.repeat(64), complete_values: item.status === 'completed', source_supported: item.status === 'completed', fields: [] })) } },
    can_save_scope: false, can_execute: false, can_finalize: false, credit_awarded: false, module_completion_eligible: false }
}
it('offers an exact failed-item retry while retaining mixed inventory and successful items', async () => {
  const run = completed('batch', completed('pilot'))
  vi.mocked(api.getBatchRun).mockResolvedValue(run)
  vi.mocked(api.getBatchWork).mockResolvedValue({ ...listing, runs: [{ run_id: run.run_id, state: run.state, phase: run.phase, input_snapshot_id: capture.uuid, prepared_at: run.prepared_at }] })
  render(<BatchAssessment enrollmentId="enrollment" definition={definition} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open batch run 1: completed' }))
  await screen.findByRole('heading', { name: 'Mixed terminal inventory · failed items remain visible' })
  expect(screen.queryByRole('button', { name: 'Prepare retry only for proposal 1' })).not.toBeInTheDocument()
  vi.mocked(api.saveBatchWork).mockRejectedValue(new Error('Synthetic response loss'))
  fireEvent.click(screen.getByRole('button', { name: 'Prepare retry only for proposal 2' }))
  await waitFor(() => expect(api.saveBatchWork).toHaveBeenCalled())
  expect(api.saveBatchWork).toHaveBeenCalledWith('enrollment', expect.objectContaining({ action: 'prepare', body: expect.objectContaining({ phase: 'retry', parent_run_id: run.run_id, parent_run_sha256: run.run_sha256, failed_source_id: 'proposal_2', previous_retry_id: null }) }))
})
it('requires fresh scope approval rather than executing when preparing a checked pilot scale-up', async () => {
  const run = completed('pilot')
  vi.mocked(api.getBatchRun).mockResolvedValue(run)
  vi.mocked(api.getBatchWork).mockResolvedValue({ ...listing, runs: [{ run_id: run.run_id, state: run.state, phase: run.phase, input_snapshot_id: capture.uuid, prepared_at: run.prepared_at }] })
  render(<BatchAssessment enrollmentId="enrollment" definition={definition} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open pilot run 1: completed' }))
  vi.mocked(api.saveBatchWork).mockRejectedValue(new Error('Synthetic response loss'))
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare three-document batch from this pilot' }))
  await waitFor(() => expect(api.saveBatchWork).toHaveBeenCalled())
  expect(api.saveBatchWork).toHaveBeenCalledWith('enrollment', expect.objectContaining({ action: 'prepare', body: expect.objectContaining({ phase: 'batch', parent_run_id: run.run_id, failed_source_id: null }) }))
})
it.each(['pilot_quality', 'capture', 'batch', 'source', 'receipt', 'previous_success'])('rejects changed %s in a saved retry lineage', change => {
  const run: BatchRun = JSON.parse(JSON.stringify(completed('retry', completed('batch', completed('pilot')))))
  if (change === 'pilot_quality') run.parent_run!.parent_run!.result!.checks!.all_values_source_supported = false
  if (change === 'capture') run.parent_run!.input_snapshot.input_snapshot_sha256 = '0'.repeat(64)
  if (change === 'batch') run.batch_id = '0'.repeat(32)
  if (change === 'source') run.failed_source_id = 'proposal_1'
  if (change === 'receipt') run.result!.item_results![0].status = 'failed'
  if (change === 'previous_success') run.previous_retry = structuredClone(completed('retry', completed('batch', completed('pilot'))))
  expect(() => verifyBatchRun(run, listing)).toThrow()
})
it('preselects the proposed batch and sends only the files the learner kept', async () => {
  vi.mocked(api.saveBatchWork).mockResolvedValue(structuredClone(capture))
  render(<BatchAssessment enrollmentId="enrollment" definition={definition} />)
  const wrong = await screen.findByRole('checkbox', { name: /nsf-proposal-alpine-ecology\.pdf/ })
  expect(screen.getAllByRole('checkbox')).toHaveLength(4)
  expect(screen.getAllByRole('checkbox').every(box => (box as HTMLInputElement).checked)).toBe(true)
  fireEvent.change(screen.getByRole('combobox', { name: 'Owned extraction' }), { target: { value: artifact } })
  fireEvent.click(wrong)
  fireEvent.click(screen.getByRole('button', { name: 'Capture extraction and selected sources' }))
  await waitFor(() => expect(api.saveBatchWork).toHaveBeenCalledOnce())
  const sent = vi.mocked(api.saveBatchWork).mock.calls[0][1] as Extract<BatchRequest, { action: 'capture' }>
  expect(sent.body.selected_source_ids).toEqual(assignedIds)
})
it('sends the consolidated cells the learner flags with the interpretation', async () => {
  const original = completed('batch', completed('pilot')), retry = completed('retry', original)
  vi.mocked(api.getBatchRun).mockResolvedValue(structuredClone(retry))
  const send = vi.fn()
  render(<BatchInterpretationForm listing={listing} original={original} initialRetries={[retry]} initialAnswer="Proposal 2 was retried; the consolidated research area for proposal 3 is wrong." locked={false} send={send} />)
  const table = await screen.findByRole('group', { name: 'Agent-consolidated table to check before export' })
  expect(within(table).getAllByRole('checkbox')).toHaveLength(15)
  fireEvent.click(within(table).getByRole('checkbox', { name: /Research Area: Biological Sciences/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save batch interpretation' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Save batch interpretation' }))
  expect(send).toHaveBeenCalledOnce()
  const sent = send.mock.calls[0][0] as Extract<BatchRequest, { action: 'review' }>
  expect(sent.body.flagged_cells).toEqual([{ source_id: 'proposal_3', field: 'Research Area' }])
  expect(validBatchRequest(sent, definition)).toBe(true)
  expect(validBatchRequest({ ...sent, body: { ...sent.body, flagged_cells: [{ source_id: 'proposal_3', field: 'Invented field' }] } }, definition)).toBe(false)
})
