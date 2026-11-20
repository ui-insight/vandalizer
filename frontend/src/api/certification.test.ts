import { afterEach, expect, it, vi } from 'vitest'
import { completeModule, downloadPreservedCertificate } from './certification'
import { apiFetch, rawFetch } from './client'
vi.mock('./client', () => ({ rawFetch: vi.fn(), apiFetch: vi.fn(), ApiError: class extends Error {} }))
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('keeps the download anchor within the initiating fullscreen dialog', async () => {
  const dialog = document.createElement('div')
  dialog.setAttribute('role', 'dialog')
  dialog.setAttribute('aria-modal', 'true')
  const button = document.createElement('button')
  dialog.appendChild(button)
  document.body.appendChild(dialog)
  button.focus()
  vi.mocked(rawFetch).mockResolvedValue({ ok: true, blob: async () => new Blob(['pdf']) } as Response)
  const revoke = vi.fn()
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:test-pdf', revokeObjectURL: revoke })
  let clickedInsideDialog = false
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clickedInsideDialog = this.parentElement === dialog
    expect(this.download).toBe('vandal-certification-preserved.pdf')
  })
  await downloadPreservedCertificate('preserved')
  expect(clickedInsideDialog).toBe(true)
  expect(document.querySelector('a')).toBeNull()
  expect(revoke).toHaveBeenCalledWith('blob:test-pdf')
})

it('pins read-only course comparisons to explicit enrollment and target identities', async () => {
  const { getUpgradeOptions, getUpgradePreview } = await import('./certification')
  const { apiFetch } = await import('./client')
  await getUpgradeOptions('learner/source')
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/upgrade-options?enrollment_id=learner%2Fsource')
  await getUpgradePreview('learner/source', 'next & course')
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/upgrade-preview?enrollment_id=learner%2Fsource&target_version=next%20%26%20course')
})

it('sends explicit selected-outcome consent and references under the pinned completion request', async () => {
  const { completeModule } = await import('./certification')
  const { apiFetch } = await import('./client')
  const selection = { review_attempt_id: '1'.repeat(32), scenario_attempt_id: '2'.repeat(32) }
  await completeModule('validation_qa', 'owned', '3'.repeat(32), selection)
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/validation_qa/complete?enrollment_id=owned&request_id=' + '3'.repeat(32), {
    method: 'POST', body: JSON.stringify({ consent: 'complete_selected_saved_outcomes', ...selection }),
  })
  await completeModule('validation_qa', 'owned', '3'.repeat(32))
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/validation_qa/complete?enrollment_id=owned&request_id=' + '3'.repeat(32), { method: 'POST' })
})

it('confirms only an original switch receipt and never sends a new target or activation consent', async () => {
  const { getCourseSelectionStatus, confirmCourseSelection } = await import('./certification')
  const { apiFetch } = await import('./client')
  await getCourseSelectionStatus()
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/selection-status')
  const receipt = { request_id: 'a'.repeat(32), kind: 'optional_upgrade_selection.1' as const, receipt_sha256: 'b'.repeat(64),
    source_enrollment_id: 'c'.repeat(32), target_enrollment_id: 'd'.repeat(32), target_course_version: 'saved', revision: 1,
    selected_at: '2026-10-07T12:00:00Z', action: 'activate_optional_upgrade' as const, credit_transferred: false as const, histories_preserved: true as const }
  await confirmCourseSelection(receipt)
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/selection-confirmations', {
    method: 'POST', body: JSON.stringify({ request_id: receipt.request_id, kind: receipt.kind, receipt_sha256: receipt.receipt_sha256,
      consent: 'confirm_original_committed_course_selection' }),
  })
})

it('stops only the reviewed preparation with separate explicit consent', async () => {
  const { stopCoursePreparation } = await import('./certification')
  const { apiFetch } = await import('./client')
  await stopCoursePreparation({ state: 'preparing', read_only: true, selection_changed: false, credit_changed: false,
    request_id: 'a'.repeat(32), preview_sha256: 'b'.repeat(64), enrollment_id: 'c'.repeat(32), course_version: 'saved',
    original_request_id: 'd'.repeat(32), write_id: 'e'.repeat(32), operation: 'activate_optional_upgrade' })
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/selection-preparation-recoveries', {
    method: 'POST', body: JSON.stringify({ request_id: 'a'.repeat(32), preview_sha256: 'b'.repeat(64),
      consent: 'stop_uncommitted_course_preparation_preserving_all_work' }),
  })
})


it('sends the original completion counter alongside the unchanged request reference', async () => {
  await completeModule('ai_literacy', 'original-enrollment', 'a'.repeat(32), undefined, 0)
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/ai_literacy/complete?enrollment_id=original-enrollment&request_id=' + 'a'.repeat(32) + '&expected_attempts=0', { method: 'POST' })
  await completeModule('ai_literacy', undefined, 'b'.repeat(32), undefined, 2)
  expect(apiFetch).toHaveBeenLastCalledWith('/api/certification/modules/ai_literacy/complete?request_id=' + 'b'.repeat(32) + '&expected_attempts=2', { method: 'POST' })
})
