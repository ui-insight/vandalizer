import { apiFetch, ApiError, rawFetch } from './client'
import type { CertificationProgress, ValidationResult, CompletionResult, CertExercise, CourseDefinition, PositionSaved, ScenarioSubmission, SavedScenarioSubmission } from '../types/certification'

function enrolledPath(path: string, enrollmentId?: string) {
  return enrollmentId ? `${path}?enrollment_id=${encodeURIComponent(enrollmentId)}` : path
}

export function getCourse(enrollmentId: string) {
  return apiFetch<CourseDefinition>(enrolledPath('/api/certification/course', enrollmentId))
}

export function getUpgradeOptions(enrollmentId: string) {
  return apiFetch<import('../types/certification').UpgradeOptions>(enrolledPath('/api/certification/upgrade-options', enrollmentId))
}

export function getUpgradePreview(enrollmentId: string, targetVersion: string) {
  return apiFetch<import('../types/certification').UpgradePreview>(
    `${enrolledPath('/api/certification/upgrade-preview', enrollmentId)}&target_version=${encodeURIComponent(targetVersion)}`)
}

export function getProgress() {
  return apiFetch<CertificationProgress>('/api/certification/progress')
}

export function getLabStatus(moduleId: string, enrollmentId?: string) {
  return apiFetch<import('../types/certification').CertificationLabStatus>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/lab-status`, enrollmentId))
}

export interface CourseSelectionReceipt {
  request_id: string
  kind: 'optional_upgrade_selection.1' | 'saved_course_selection.1'
  receipt_sha256: string
  source_enrollment_id: string
  target_enrollment_id: string
  target_course_version: string
  target_manifest_sha256?: string
  revision: number
  selected_at: string
  action: 'activate_optional_upgrade' | 'return_to_original_course' | 'resume_upgraded_course'
  credit_transferred: false
  histories_preserved: true
}

export interface CourseSelectionStatus {
  read_only: true
  current_enrollment_id: string | null
  pending: CourseSelectionReceipt | null
  preparation?: CoursePreparationStatus
}

export interface CoursePreparationStatus {
  state: 'preparing' | 'recovery_pending'
  read_only: true
  selection_changed: false
  credit_changed: false
  request_id: string
  preview_sha256: string
  enrollment_id: string
  course_version: string
  original_request_id: string
  write_id: string
  operation: 'activate_optional_upgrade' | 'select_saved_course'
}

export function stopCoursePreparation(preparation: CoursePreparationStatus) {
  return apiFetch<{ kind: 'selection_preparation_recovery.1'; recovery_id: string; enrollment_id: string;
    original_request_id: string; original_write_id: string; status: 'preparation_stopped';
    selection_changed: false; credit_changed: false; assessments_repeated: false }>('/api/certification/selection-preparation-recoveries', {
    method: 'POST', body: JSON.stringify({ request_id: preparation.request_id, preview_sha256: preparation.preview_sha256,
      consent: 'stop_uncommitted_course_preparation_preserving_all_work' }),
  })
}

export function getCourseSelectionStatus() {
  return apiFetch<CourseSelectionStatus>('/api/certification/selection-status')
}

export function confirmCourseSelection(receipt: CourseSelectionReceipt) {
  return apiFetch<{ confirmed: true; selection_changed: false; receipt: CourseSelectionReceipt }>('/api/certification/selection-confirmations', {
    method: 'POST', body: JSON.stringify({ request_id: receipt.request_id, kind: receipt.kind,
      receipt_sha256: receipt.receipt_sha256, consent: 'confirm_original_committed_course_selection' }),
  })
}

export function getPracticalHistoryCourses() {
  return apiFetch<import('../types/certification').PracticalHistoryCourses>('/api/certification/practical-history')
}

export function getPracticalHistoryCourse(enrollmentId: string) {
  return apiFetch<import('../types/certification').PracticalHistoryCourse>(`/api/certification/practical-history/${encodeURIComponent(enrollmentId)}`)
}

export function getSavedScenarioHistory(enrollmentId: string, moduleId: string) {
  return apiFetch<import('../types/certification').ScenarioHistoryList>(`/api/certification/practical-history/${encodeURIComponent(enrollmentId)}/modules/${encodeURIComponent(moduleId)}/scenarios`)
}

export function getSavedScenarioHistoryResult(enrollmentId: string, moduleId: string, attemptId: string) {
  return apiFetch<import('../types/certification').ScenarioHistoryResult>(`/api/certification/practical-history/${encodeURIComponent(enrollmentId)}/modules/${encodeURIComponent(moduleId)}/scenarios/${encodeURIComponent(attemptId)}`)
}

export function savePosition(enrollmentId: string, moduleId: string, lessonId: string, expectedRevision: number) {
  return apiFetch<PositionSaved>(enrolledPath('/api/certification/position', enrollmentId), {
    method: 'PUT', body: JSON.stringify({ module_id: moduleId, lesson_id: lessonId, expected_revision: expectedRevision }),
  })
}

export function validateModule(moduleId: string, enrollmentId?: string) {
  return apiFetch<ValidationResult>(enrolledPath(`/api/certification/modules/${moduleId}/validate`, enrollmentId), { method: 'POST' })
}

export function completeModule(moduleId: string, enrollmentId?: string, requestId?: string, selection?: import('../types/certification').OutcomeCompletionSelection, expectedAttempts?: number) {
  let path = enrolledPath(`/api/certification/modules/${moduleId}/complete`, enrollmentId)
  if (requestId) path += `${enrollmentId ? '&' : '?'}request_id=${encodeURIComponent(requestId)}`
  if (expectedAttempts !== undefined) path += `${path.includes('?') ? '&' : '?'}expected_attempts=${expectedAttempts}`
  return apiFetch<CompletionResult>(path, { method: 'POST', ...(selection ? { body: JSON.stringify({ consent: 'complete_selected_saved_outcomes', ...selection }) } : {}) })
}

export function provisionModule(moduleId: string, enrollmentId?: string) {
  return apiFetch<{ provisioned_docs: string[] }>(
    enrolledPath(`/api/certification/modules/${moduleId}/provision`, enrollmentId),
    { method: 'POST' },
  )
}

export function getExercise(moduleId: string, enrollmentId?: string) {
  return apiFetch<CertExercise>(enrolledPath(`/api/certification/modules/${moduleId}/exercise`, enrollmentId))
}

export function submitAssessment(moduleId: string, answers: Record<string, string>, enrollmentId?: string) {
  return apiFetch<{ stored: boolean }>(
    enrolledPath(`/api/certification/modules/${moduleId}/assessment`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ answers }) },
  )
}

export interface PreservedCredential {
  credential_scope?: import('../types/certification').CredentialScope
  credential_id: string
  enrollment_id: string
  learner_name: string
  course_title: string
  course_version: string | null
  certified_at: string | null
  provenance: string
}

export function getCredentials() {
  return apiFetch<{ credentials: PreservedCredential[] }>('/api/certification/credentials')
}

export function downloadPreservedCertificate(credentialId: string) {
  return downloadPdf(`/api/certification/credentials/${encodeURIComponent(credentialId)}/certificate`, `vandal-certification-${credentialId}.pdf`)
}

/** Download the caller's certificate PDF. The server 404s until they are certified. */
export async function downloadCertificate(enrollmentId?: string): Promise<void> {
  return downloadPdf(enrolledPath('/api/certification/certificate', enrollmentId))
}

async function downloadPdf(path: string, filename = 'vandal-workflow-architect-certificate.pdf'): Promise<void> {
  // A fullscreen learning panel traps outside clicks, including a temporary
  // download anchor. Retain the initiating dialog across the network request.
  const host = document.activeElement?.closest('[role="dialog"][aria-modal="true"]')
  const res = await rawFetch(path, { method: 'GET' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Download failed' }))
    throw new ApiError(res.status, body.detail || 'Download failed')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  ;(host?.isConnected ? host : document.body).appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}


export function submitScenarios(enrollmentId: string, moduleId: string, requestId: string, bankSha256: string, answers: Record<string, string>) {
  return apiFetch<ScenarioSubmission>(enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/scenarios`, enrollmentId), {
    method: 'POST', body: JSON.stringify({ request_id: requestId, bank_sha256: bankSha256, answers }),
  })
}

export function getScenarioSubmission(attemptId: string) {
  return apiFetch<SavedScenarioSubmission>(`/api/certification/scenario-attempts/${encodeURIComponent(attemptId)}`)
}

export function getPracticalRuns(enrollmentId: string, moduleId: string) {
  return apiFetch<{ runs: { run_id: string; state: string }[]; older_runs_available: boolean; enrollment_id?: string; module_id?: string; read_only_reason?: string | null }>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/practical-runs`, enrollmentId))
}

export function preparePracticalRun(enrollmentId: string, moduleId: string, body: import('../types/certification').PracticalPreparationBody) {
  return apiFetch<import('../types/certification').SavedPracticalPreparation>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/practical-runs`, enrollmentId),
    { method: 'POST', body: JSON.stringify(body) })
}

export function getPracticalPreparation(enrollmentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedPracticalPreparation>(
    enrolledPath(`/api/certification/practical-preparations/${encodeURIComponent(requestId)}`, enrollmentId))
}

export function getPracticalExecution(enrollmentId: string, runId: string) {
  return apiFetch<import('../types/certification').SavedPracticalExecution>(
    enrolledPath(`/api/certification/practical-runs/${encodeURIComponent(runId)}/execution`, enrollmentId))
}

export function executePracticalRun(enrollmentId: string, runId: string, body: import('../types/certification').PracticalExecutionBody) {
  return apiFetch<import('../types/certification').SavedPracticalExecution>(
    enrolledPath(`/api/certification/practical-runs/${encodeURIComponent(runId)}/execution`, enrollmentId),
    { method: 'POST', body: JSON.stringify(body) })
}

export function getPracticalDecisionContext(enrollmentId: string, moduleId: string, promptId: string, runId: string) {
  return apiFetch<import('../types/certification').PracticalDecisionContext>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/decisions/${encodeURIComponent(promptId)}/runs/${encodeURIComponent(runId)}`, enrollmentId))
}

export function submitPracticalDecision(enrollmentId: string, moduleId: string, promptId: string, body: import('../types/certification').PracticalDecisionBody) {
  return apiFetch<import('../types/certification').SavedPracticalDecision>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/decisions/${encodeURIComponent(promptId)}`, enrollmentId),
    { method: 'POST', body: JSON.stringify(body) })
}

export function getPracticalDecision(decisionId: string) {
  return apiFetch<import('../types/certification').SavedPracticalDecision>(`/api/certification/learner-decisions/${encodeURIComponent(decisionId)}`)
}

export function getAutomaticReviews(enrollmentId: string, moduleId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReviewList>(
    enrolledPath(`/api/certification/modules/${encodeURIComponent(moduleId)}/automatic-reviews`, enrollmentId))
}

export function getAutomaticReview(enrollmentId: string, attemptId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(
    enrolledPath(`/api/certification/automatic-reviews/${encodeURIComponent(attemptId)}`, enrollmentId))
}

export function requestAutomaticReview(enrollmentId: string, runId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(
    enrolledPath(`/api/certification/practical-runs/${encodeURIComponent(runId)}/automatic-reviews`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}

export function retryAutomaticReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(
    enrolledPath(`/api/certification/automatic-reviews/${encodeURIComponent(parentId)}/retry`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}


export function getProcessDesigns(enrollmentId: string) {
  return apiFetch<import('../types/certification').ProcessSubmissionList>(enrolledPath('/api/certification/modules/process_mapping/process-designs', enrollmentId))
}
export function saveProcessDesign(enrollmentId: string, body: import('../types/certification').ProcessSubmissionBody) {
  return apiFetch<import('../types/certification').SavedProcessSubmission>(enrolledPath('/api/certification/modules/process_mapping/process-designs', enrollmentId),
    { method: 'POST', body: JSON.stringify(body) })
}
export function getProcessDesign(enrollmentId: string, submissionId: string) {
  return apiFetch<import('../types/certification').SavedProcessSubmission>(enrolledPath(`/api/certification/process-designs/${encodeURIComponent(submissionId)}`, enrollmentId))
}
export function requestProcessReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/process-designs/${encodeURIComponent(submissionId)}/automatic-reviews`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryProcessReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/process-automatic-reviews/${encodeURIComponent(parentId)}/retry`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}


export function getWorkflowDesigns(enrollmentId: string) {
  return apiFetch<import('../types/certification').WorkflowDesignList>(enrolledPath('/api/certification/modules/workflow_design/designs', enrollmentId))
}
export function captureWorkflowDesign(enrollmentId: string, body: import('../types/certification').WorkflowDesignCaptureBody) {
  return apiFetch<import('../types/certification').SavedWorkflowDesignCapture>(enrolledPath('/api/certification/modules/workflow_design/design-captures', enrollmentId), { method: 'POST', body: JSON.stringify(body) })
}
export function getWorkflowDesignCapture(enrollmentId: string, snapshotId: string) {
  return apiFetch<import('../types/certification').SavedWorkflowDesignCapture>(enrolledPath(`/api/certification/workflow-design-captures/${encodeURIComponent(snapshotId)}`, enrollmentId))
}
export function approveWorkflowDesign(enrollmentId: string, body: import('../types/certification').WorkflowDesignSubmissionBody) {
  return apiFetch<import('../types/certification').SavedWorkflowDesignSubmission>(enrolledPath('/api/certification/modules/workflow_design/designs', enrollmentId), { method: 'POST', body: JSON.stringify(body) })
}
export function getWorkflowDesign(enrollmentId: string, submissionId: string) {
  return apiFetch<import('../types/certification').SavedWorkflowDesignSubmission>(enrolledPath(`/api/certification/workflow-designs/${encodeURIComponent(submissionId)}`, enrollmentId))
}
export function requestWorkflowDesignReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/workflow-designs/${encodeURIComponent(submissionId)}/automatic-reviews`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}

export function requestConnectedReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/connected-reviews/${encodeURIComponent(submissionId)}/automatic-reviews`, enrollmentId), { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function requestBudgetReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/budget-reviews/${encodeURIComponent(submissionId)}/automatic-reviews?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryBudgetReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/budget-automatic-reviews/${encodeURIComponent(parentId)}/retry?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}
export function retryConnectedReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/connected-automatic-reviews/${encodeURIComponent(parentId)}/retry`, enrollmentId), { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}
export function retryWorkflowDesignReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(enrolledPath(`/api/certification/workflow-design-automatic-reviews/${encodeURIComponent(parentId)}/retry`, enrollmentId),
    { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}


export function requestOutputReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/output-reviews/${encodeURIComponent(submissionId)}/automatic-reviews?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryOutputReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/output-automatic-reviews/${encodeURIComponent(parentId)}/retry?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}

export function requestValidationReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/validation-reviews/${encodeURIComponent(submissionId)}/automatic-reviews?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryValidationReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/validation-automatic-reviews/${encodeURIComponent(parentId)}/retry?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}

export function requestBatchReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/batch-reviews/${encodeURIComponent(submissionId)}/automatic-reviews?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryBatchReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/batch-automatic-reviews/${encodeURIComponent(parentId)}/retry?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}

export function requestGovernanceReview(enrollmentId: string, submissionId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/governance-reviews/${encodeURIComponent(submissionId)}/automatic-reviews?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'assess_saved_work' }) })
}
export function retryGovernanceReview(enrollmentId: string, parentId: string, requestId: string) {
  return apiFetch<import('../types/certification').SavedAutomaticReview>(`/api/certification/governance-automatic-reviews/${encodeURIComponent(parentId)}/retry?enrollment_id=${encodeURIComponent(enrollmentId)}`, { method: 'POST', body: JSON.stringify({ request_id: requestId, consent: 'retry_saved_assessment' }) })
}
