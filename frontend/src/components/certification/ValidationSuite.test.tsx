import repairFixtureJson from './__fixtures__/validation-repair-http.json?raw'
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/validationSuite'
import { ApiError } from '../../api/client'
import type { ValidationCapture, ValidationCase, ValidationList, ValidationRequest, ValidationRun } from '../../types/validationSuite'
import { ValidationSuite } from './ValidationSuite'
import { useValidationRequest } from './useValidationRequest'
import { validValidationRequest, verifyValidationResponse } from './validationSuiteState'
vi.mock('../../api/validationSuite', () => ({ getValidationWork: vi.fn(), getValidationCapture: vi.fn(), getValidationSuite: vi.fn(), getValidationRun: vi.fn(), getValidationScope: vi.fn(), getValidationReview: vi.fn(), saveValidationWork: vi.fn(), getValidationSource: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved feedback</p> }))
const definition: ValidationCase = { id: 'case', revision: 1, module_id: 'validation_qa', case_sha256: 'a'.repeat(64),
  provenance: 'authored_validation_assignment_not_observed_failure_or_retest', notice: 'Draft feedback only', task: 'Check a complete representative suite.',
  instructions: ['Inspect both sources.'], exclusions: ['No staff review.'], flawed_proposal: 'Use annual totals.',
  fields: [{ title: 'Principal Investigator', meaning: 'Lead PI', comparison: 'person_name' }, { title: 'Total Project Budget', meaning: 'Full budget', comparison: 'usd_amount' }, { title: 'Named Co-PI', meaning: 'Explicit Co-PI only', comparison: 'person_name_or_explicit_absence' }],
  sources: [{ id: 'nsf', filename: 'nsf.pdf', sha256: 'b'.repeat(64), coverage: 'Annual ambiguity' }, { id: 'nih', filename: 'nih.pdf', sha256: 'c'.repeat(64), coverage: 'Absent Co-PI' }],
  questions: [{ id: 'suite_design', phase: 'before_original_run', prompt: 'Explain coverage and limitations.' }, { id: 'repair_review', phase: 'after_complete_retest', prompt: 'Explain causal repair and full retest.' }] }
const identity = { enrollment_id: 'enrollment', module_id: 'validation_qa' as const, course_version: 'draft', manifest_sha256: 'd'.repeat(64) }
const artifact = 'e'.repeat(32), snapshotId = 'f'.repeat(32)
const request: ValidationRequest = { action: 'capture', body: { request_id: snapshotId, artifact_id: artifact, case_sha256: definition.case_sha256, consent: 'capture_validation_extraction_and_complete_sources' } }
const key = `certification-validation-request:enrollment:${definition.case_sha256}`
const capture: ValidationCapture = { ...identity, uuid: snapshotId, case: definition, input_snapshot_sha256: '1'.repeat(64), artifact_id: artifact, artifact_sha256: '2'.repeat(64), captured_at: '2026-10-07', execution_authorized: false, credit_awarded: false,
  artifact: { uuid: artifact, title: 'Original extraction', fields: definition.fields.map((f, i) => ({ id: String(i), title: f.title, searchphrase: f.meaning, is_optional: i === 2, enum_values: [] })) },
  documents: definition.sources.map(s => ({ source_id: s.id, document_id: s.id, assigned_filename: s.filename, source_sha256: s.sha256, pages: ['Original source page'], text: 'Original source page' })) }
const listing: ValidationList = { ...identity, case: definition, can_submit: true, read_only_reason: null, extractions: [{ artifact_id: artifact, title: 'Original extraction' }], older_extractions_available: false,
  assigned_sources: [], captures: [{ input_snapshot_id: snapshotId, extraction_name: 'Original extraction', captured_at: '2026-10-07' }], older_captures_available: false, suites: [], older_suites_available: false, runs: [], older_runs_available: false, submissions: [], older_submissions_available: false }
beforeEach(() => { vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear(); vi.mocked(api.getValidationWork).mockResolvedValue(structuredClone(listing)); vi.mocked(api.getValidationCapture).mockResolvedValue(structuredClone(capture)) })
it('opens original sources in history without capture, expectation forms or mutations', async () => {
  render(<ValidationSuite enrollmentId="enrollment" definition={definition} historyOnly />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open capture 1: Original extraction' }))
  await screen.findByRole('button', { name: 'Download original NIH PDF' })
  expect(screen.queryByRole('form', { name: 'Capture validation extraction' })).not.toBeInTheDocument()
  expect(screen.queryByRole('form', { name: 'Save representative test expectations' })).not.toBeInTheDocument()
  expect(api.saveValidationWork).not.toHaveBeenCalled()
})
it('requires six original expectations including explicit absence and source explanations', async () => {
  render(<ValidationSuite enrollmentId="enrollment" definition={definition} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open capture 1: Original extraction' }))
  await screen.findByRole('form', { name: 'Save representative test expectations' })
  expect(screen.getAllByRole('group', { name: /^(NSF|NIH) ·/ })).toHaveLength(6)
  expect(screen.getAllByRole('textbox', { name: 'Expected value' })).toHaveLength(6)
  fireEvent.change(screen.getAllByRole('combobox', { name: 'Expectation type' })[5], { target: { value: 'explicit_absence' } })
  expect(screen.getAllByRole('textbox', { name: 'Expected value' })).toHaveLength(5)
  fireEvent.submit(screen.getByRole('form', { name: 'Save representative test expectations' }))
  await screen.findByRole('alert')
  expect(api.saveValidationWork).not.toHaveBeenCalled()
})
it('persists before POST and recovers a lost capture reply with GET only', async () => {
  const onSaved = vi.fn()
  vi.mocked(api.saveValidationWork).mockImplementation(async () => { expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(request); throw new Error('Lost reply') })
  const hook = renderHook(() => useValidationRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.check() })
  expect(api.saveValidationWork).toHaveBeenCalledOnce()
  expect(api.getValidationCapture).toHaveBeenCalledWith('enrollment', snapshotId)
  expect(onSaved).toHaveBeenCalledWith(capture, 'capture')
  expect(sessionStorage.getItem(key)).toBeNull()
})
it('restores pending identity after remount and requires explicit finish for missing saved work', async () => {
  sessionStorage.setItem(key, JSON.stringify(request))
  vi.mocked(api.getValidationCapture).mockRejectedValue(new ApiError(404, 'Missing'))
  vi.mocked(api.saveValidationWork).mockResolvedValue(capture)
  const hook = renderHook(() => useValidationRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.pending).toEqual(request))
  await act(async () => { await hook.result.current.check() })
  expect(hook.result.current.canFinish).toBe(true)
  expect(api.saveValidationWork).not.toHaveBeenCalled()
  await act(async () => { await hook.result.current.finish() })
  expect(api.saveValidationWork).toHaveBeenCalledWith('enrollment', request)
})
it('blocks new writes when pending storage is malformed', async () => {
  sessionStorage.setItem(key, '{broken')
  const hook = renderHook(() => useValidationRequest(listing, vi.fn()))
  await waitFor(() => expect(hook.result.current.blocked).toBe(true))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveValidationWork).not.toHaveBeenCalled()
})
it('does not send when the original request cannot be preserved', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage full') })
  const hook = renderHook(() => useValidationRequest(listing, vi.fn()))
  await act(async () => { await hook.result.current.send(request) })
  expect(api.saveValidationWork).not.toHaveBeenCalled()
  expect(hook.result.current.error).toMatch(/no request was sent/)
})
it('leaves an ambiguous mismatched response pending and rejects another write', async () => {
  vi.mocked(api.saveValidationWork).mockResolvedValue({ ...capture, enrollment_id: 'foreign' })
  const onSaved = vi.fn(), hook = renderHook(() => useValidationRequest(listing, onSaved))
  await act(async () => { await hook.result.current.send(request) })
  expect(hook.result.current.pending).toEqual(request)
  await act(async () => { await hook.result.current.send({ ...request, body: { ...request.body, request_id: '9'.repeat(32) } }) })
  expect(onSaved).not.toHaveBeenCalled(); expect(api.saveValidationWork).toHaveBeenCalledOnce()
})
it.each(['case', 'source', 'artifact', 'credit'])('rejects changed %s identity in capture evidence', change => {
  const wrong = structuredClone(capture)
  if (change === 'case') wrong.case.case_sha256 = '9'.repeat(64)
  if (change === 'source') wrong.documents[1].source_sha256 = '9'.repeat(64)
  if (change === 'artifact') wrong.artifact.uuid = '9'.repeat(32)
  if (change === 'credit') Object.assign(wrong, { credit_awarded: true })
  expect(() => verifyValidationResponse(wrong, listing, request)).toThrow()
})
it('rejects saved requests missing the case or carrying a different course assignment', () => {
  expect(validValidationRequest({ ...request, body: { ...request.body, case_sha256: undefined } } as unknown as ValidationRequest, definition)).toBe(false)
  expect(validValidationRequest({ ...request, body: { ...request.body, case_sha256: '0'.repeat(64) } }, definition)).toBe(false)
})

it('opens the fixed original extraction for repair without changing the failure or its expectations', async () => {
  // Real disposable HTTP response, with synthetic provider results and no earned credit.
  const fixture = JSON.parse(repairFixtureJson) as { listing: ValidationList; original: ValidationRun }
  vi.mocked(api.getValidationWork).mockResolvedValue(fixture.listing)
  vi.mocked(api.getValidationRun).mockResolvedValue(fixture.original)
  const before = JSON.stringify(fixture.original)
  render(<ValidationSuite enrollmentId={fixture.listing.enrollment_id} definition={fixture.listing.case} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open original run 1: completed' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Use this original failure for repair' }))
  expect(screen.getByLabelText('Owned extraction')).toBeDisabled()
  const link = screen.getByRole('link', { name: 'Open selected extraction in a new tab' })
  expect(new URL(link.getAttribute('href')!, 'http://localhost').searchParams.get('extraction')).toBe(fixture.original.input_snapshot.artifact_id)
  expect(api.saveValidationWork).not.toHaveBeenCalled()
  expect(JSON.stringify(fixture.original)).toBe(before)
})
