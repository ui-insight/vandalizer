import { apiFetch, rawFetch } from './client'
import type { Workflow, WorkflowStatus } from '../types/workflow'

// Workflow CRUD

export function createWorkflow(data: { name: string; description?: string }) {
  return apiFetch<Workflow>('/api/workflows', { method: 'POST', body: JSON.stringify(data) })
}

export function listWorkflows(params?: { scope?: string; search?: string }) {
  const sp = new URLSearchParams()
  if (params?.scope) sp.set('scope', params.scope)
  if (params?.search) sp.set('search', params.search)
  const qs = sp.toString()
  return apiFetch<Workflow[]>(`/api/workflows${qs ? `?${qs}` : ''}`)
}

export function getWorkflow(id: string, shareToken?: string) {
  const qs = shareToken ? `?share_token=${encodeURIComponent(shareToken)}` : ''
  return apiFetch<Workflow>(`/api/workflows/${id}${qs}`)
}

export function mintWorkflowShareToken(id: string) {
  return apiFetch<{ share_token: string }>(
    `/api/workflows/${id}/share-token`,
    { method: 'POST' },
  )
}

export function updateWorkflow(
  id: string,
  data: {
    name?: string;
    description?: string;
    input_config?: Record<string, unknown>;
    output_config?: Record<string, unknown>;
  },
) {
  return apiFetch<Workflow>(`/api/workflows/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteWorkflow(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/${id}`, { method: 'DELETE' })
}

export function duplicateWorkflow(id: string, shareToken?: string) {
  const qs = shareToken ? `?share_token=${encodeURIComponent(shareToken)}` : ''
  return apiFetch<Workflow>(`/api/workflows/${id}/duplicate${qs}`, { method: 'POST' })
}

// Unset team_id on the workflow. The workflow stays, but disappears from
// the team library. Creator keeps personal access.
export function removeWorkflowFromTeam(id: string) {
  return apiFetch<Workflow>(`/api/workflows/${id}/team`, { method: 'DELETE' })
}

// Steps

export function addStep(workflowId: string, data: { name: string; data?: Record<string, unknown>; is_output?: boolean }) {
  return apiFetch(`/api/workflows/${workflowId}/steps`, { method: 'POST', body: JSON.stringify(data) })
}

export function updateStep(stepId: string, data: { name?: string; data?: Record<string, unknown>; is_output?: boolean }) {
  return apiFetch(`/api/workflows/steps/${stepId}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteStep(stepId: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/steps/${stepId}`, { method: 'DELETE' })
}

// Tasks

export function addTask(stepId: string, data: { name: string; data?: Record<string, unknown> }) {
  return apiFetch<{ id: string; name: string; data: Record<string, unknown> }>(
    `/api/workflows/steps/${stepId}/tasks`,
    { method: 'POST', body: JSON.stringify(data) },
  )
}

export function updateTask(taskId: string, data: { name?: string; data?: Record<string, unknown> }) {
  return apiFetch<{ id: string; name: string; data: Record<string, unknown> }>(`/api/workflows/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteTask(taskId: string) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/tasks/${taskId}`, { method: 'DELETE' })
}

// Prompt improvement

export interface PromptImprovement {
  improved_prompt: string
  rationale: string[]
}

export function improvePrompt(data: {
  prompt: string
  input_source?: string
  prev_step_name?: string
  sample_input?: string
}) {
  return apiFetch<PromptImprovement>('/api/workflows/improve-prompt', {
    method: 'POST',
    body: JSON.stringify(data),
    timeoutMs: 90_000,
  })
}

// Execution

export function runWorkflow(workflowId: string, data: { document_uuids: string[]; model?: string; batch_mode?: boolean }) {
  return apiFetch<{ session_id?: string; batch_id?: string; activity_id?: string }>(`/api/workflows/${workflowId}/run`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getWorkflowStatus(sessionId: string) {
  return apiFetch<WorkflowStatus>(`/api/workflows/status?session_id=${encodeURIComponent(sessionId)}`)
}

// Stop an in-flight single run. The backend flips the result to "canceled" and
// revokes the Celery task (terminate) so a mid-step run is interrupted.
export function cancelWorkflow(sessionId: string) {
  return apiFetch<{ session_id: string; status: string }>(
    `/api/workflows/sessions/${encodeURIComponent(sessionId)}/cancel`,
    { method: 'POST' },
  )
}

export interface BatchStatusItem {
  session_id: string
  document_title: string | null
  status: string
  num_steps_completed: number
  num_steps_total: number
  current_step_name: string | null
  final_output: unknown
}

export interface BatchStatus {
  status: string
  total: number
  completed: number
  failed: number
  items: BatchStatusItem[]
}

export function getBatchStatus(batchId: string) {
  return apiFetch<BatchStatus>(`/api/workflows/batch-status?batch_id=${encodeURIComponent(batchId)}`)
}

export function streamWorkflowStatus(
  sessionId: string,
  onStatus: (status: WorkflowStatus) => void,
  onError?: (err: unknown) => void,
): () => void {
  let aborted = false
  const controller = new AbortController()

  const url = `/api/workflows/status/stream?session_id=${encodeURIComponent(sessionId)}`

  ;(async () => {
    try {
      const res = await fetch(url, {
        credentials: 'include',
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        onError?.(new Error('Failed to connect to workflow status stream'))
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!aborted) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error === 'not_found') {
              onError?.(new Error('Workflow result not found'))
              return
            }
            onStatus(data as WorkflowStatus)
            if (
              data.status === 'completed' ||
              data.status === 'error' ||
              data.status === 'failed' ||
              data.status === 'canceled'
            ) {
              return
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err) {
      if (!aborted) onError?.(err)
    }
  })()

  // Return cleanup function
  return () => {
    aborted = true
    controller.abort()
  }
}

export function testStep(data: { task_name: string; task_data: Record<string, unknown>; document_uuids: string[]; model?: string }) {
  return apiFetch<{ task_id: string }>('/api/workflows/steps/test', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getTestStepStatus(taskId: string) {
  return apiFetch<{ status: string; result?: unknown; error?: string }>(`/api/workflows/steps/test/${taskId}`)
}

export function downloadResults(sessionId: string, format: string = 'json', opts?: { parseStructured?: boolean }) {
  const params = new URLSearchParams({ session_id: sessionId, format })
  if (opts?.parseStructured) params.set('parse_structured', 'true')
  return `/api/workflows/download?${params.toString()}`
}

export type SaveOutputFormat = 'pdf' | 'markdown' | 'csv' | 'json' | 'text'

export function saveResultToFolder(
  sessionId: string,
  data: { folder_uuid: string; format: SaveOutputFormat; file_name?: string },
) {
  return apiFetch<{ ok: boolean; folder_uuid: string; file_path: string }>(
    `/api/workflows/sessions/${encodeURIComponent(sessionId)}/save-to-folder`,
    { method: 'POST', body: JSON.stringify(data) },
  )
}

// Export / Import

export function exportWorkflowUrl(id: string) {
  return `/api/workflows/${id}/export`
}

export async function importWorkflow(file: File): Promise<Workflow> {
  const form = new FormData()
  form.append('file', file)
  const res = await rawFetch('/api/workflows/import', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Import failed' }))
    throw new Error(body.detail || 'Import failed')
  }
  return res.json()
}

export async function importIntoWorkflow(workflowId: string, file: File): Promise<Workflow> {
  const form = new FormData()
  form.append('file', file)
  const res = await rawFetch(`/api/workflows/${workflowId}/import`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Import failed' }))
    throw new Error(body.detail || 'Import failed')
  }
  return res.json()
}

// Step reordering

export function reorderSteps(workflowId: string, stepIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/workflows/${workflowId}/reorder-steps`, {
    method: 'POST',
    body: JSON.stringify({ step_ids: stepIds }),
  })
}

// Validation Plan

export interface ValidationCheckDefinition {
  id: string
  name: string
  description: string
  category?: string
  // Step the check is primarily about — drives the per-step breakdown.
  // Auto-generated plans always populate this now; older plans may omit it.
  target_step?: string
  // "auto" (LLM-generated) or "manual" (user-authored). Regenerating the
  // plan replaces auto checks but preserves manual ones. Older checks omit
  // this and are treated as auto.
  source?: 'auto' | 'manual'
}

export interface ValidationPlanResponse {
  checks: ValidationCheckDefinition[]
  // Stale-plan detection: true when the workflow definition changed since the
  // plan was generated/saved, or when checks target steps that no longer
  // exist. PUT/generate responses always come back fresh (false).
  plan_stale?: boolean
  stale_reasons?: string[] // 'definition_changed' | 'orphaned_checks'
  orphaned_check_ids?: string[]
}

export function getValidationPlan(workflowId: string) {
  return apiFetch<ValidationPlanResponse>(`/api/workflows/${workflowId}/validation-plan`)
}

export function updateValidationPlan(workflowId: string, checks: ValidationCheckDefinition[]) {
  return apiFetch<ValidationPlanResponse>(`/api/workflows/${workflowId}/validation-plan`, {
    method: 'PUT',
    body: JSON.stringify({ checks }),
  })
}

export function generateValidationPlan(workflowId: string) {
  return apiFetch<ValidationPlanResponse>(`/api/workflows/${workflowId}/validation-plan/generate`, {
    method: 'POST',
  })
}

// URL for downloading the latest validation run as a report file. Auth is
// cookie-based, so window.open() carries credentials (mirrors exportWorkflowUrl).
export function validationReportUrl(workflowId: string, format: 'md' | 'json' = 'md') {
  return `/api/workflows/${workflowId}/validation-report?format=${encodeURIComponent(format)}`
}

// Validation Inputs

export interface ValidationInputDefinition {
  id: string
  type: 'document' | 'text'
  document_uuid?: string
  document_title?: string
  document_exists?: boolean
  text?: string
  label?: string
}

export function getValidationInputs(workflowId: string) {
  return apiFetch<{ inputs: ValidationInputDefinition[] }>(`/api/workflows/${workflowId}/validation-inputs`)
}

export function updateValidationInputs(workflowId: string, inputs: ValidationInputDefinition[]) {
  return apiFetch<{ inputs: ValidationInputDefinition[] }>(`/api/workflows/${workflowId}/validation-inputs`, {
    method: 'PUT',
    body: JSON.stringify({ inputs }),
  })
}

export function createTempDocuments(workflowId: string, texts: { text: string; label: string }[]) {
  return apiFetch<{ document_uuids: string[] }>(`/api/workflows/${workflowId}/create-temp-documents`, {
    method: 'POST',
    body: JSON.stringify({ texts }),
  })
}

// Validation Execution

export interface ValidationCheck {
  name: string
  status: 'PASS' | 'FAIL' | 'WARN' | 'SKIP'
  detail: string | null
  check_id?: string
}

export interface ValidationResult {
  grade: string
  summary: string
  checks: ValidationCheck[]
  // Phase 2A diagnostic: how the workflow scores against a single-shot LLM
  // counterfactual. lift_vs_no_workflow is positive when the workflow earns
  // its complexity, negative when a single prompt would do as well or better.
  baseline_no_workflow_score?: number | null
  lift_vs_no_workflow?: number | null
  baseline_no_workflow_detail?: {
    score: number
    output: string
    weighted_pass_rate: number
    checks: Array<{ check_id?: string; status: string }>
  } | null
  // Surfaced for the lift readout — quality_score is the workflow's own
  // score (separate from the overall score that blends in stability).
  quality_score?: number
  // Per-step quality breakdown — drives the "which step is weak?" UI.
  // Empty array when the workflow has a single step (the breakdown wouldn't
  // add information vs. the overall grade in that case).
  step_breakdown?: Array<{
    step: string
    score: number       // 0-100
    pass: number
    warn: number
    fail: number
    skip: number
    total: number
    evaluated: number
    // Per-step judge variance (0-1 scale). Multiply by 1.96 × 100 for a
    // ±N pts confidence interval on this step's score. Omitted when the
    // bucket had too few samples to compute (single check on the step).
    variance?: number | null
  }>
  // Judge nondeterminism (0-1 scale). UI multiplies by 1.96 × 100 to render
  // a 95% confidence interval in points on the grade score. Null when not
  // enough comparable verdicts to compute.
  judge_variance?: number | null
  // Deterministic structural + runtime diagnostics — the things the LLM
  // judge can't reliably catch (dangling search-set refs, prompts
  // referencing unproduced fields, empty/error-shaped step outputs,
  // "claims JSON" outputs that don't parse). Always an array — empty when
  // the workflow is clean.
  static_diagnostics?: Array<{
    code: string
    level: 'error' | 'warning' | 'info'
    message: string
    target_step?: string | null
    details?: Record<string, unknown>
  }>
  // True when this run was graded against a plan that no longer matches the
  // workflow definition — the grade card renders a regenerate caveat so a
  // low grade isn't mistaken for a bad workflow.
  plan_stale?: boolean
}

export function validateWorkflow(workflowId: string) {
  return apiFetch<ValidationResult>(`/api/workflows/${workflowId}/validate`, {
    method: 'POST',
  })
}

// ---------------------------------------------------------------------------
// Test-case generator — proposes past WorkflowResults as expected outputs so
// the optimizer doesn't hard-error with "No test inputs available".
// ---------------------------------------------------------------------------

export interface TestCaseProposal {
  session_id: string
  suggested_label: string
  output_preview: string
  output_length: number
  confidence: number  // 0-1
  why: string
  already_saved: boolean
  created_at: string | null
}

export interface TestCaseProposeResponse {
  proposals: TestCaseProposal[]
  skipped: {
    empty_or_error: number
    too_short: number
    duplicates: number
  }
  synthesized: false
  note?: string
}

export interface TestCaseSynthesizeResponse {
  label: string
  text: string
  synthesized: true
}

export interface TestCaseAcceptResponse {
  accepted: Array<{
    id: string
    type: 'expected_output'
    session_id: string
    label: string
    output_text: string
    source: 'test_case_generator'
  }>
  skipped: Array<{ session_id: string; reason: string }>
}

export function proposeTestCases(workflowId: string, limit = 5) {
  return apiFetch<TestCaseProposeResponse>(
    `/api/workflows/${workflowId}/test-cases/propose`,
    { method: 'POST', body: JSON.stringify({ limit }) },
  )
}

export function synthesizeTestCase(workflowId: string) {
  return apiFetch<TestCaseSynthesizeResponse>(
    `/api/workflows/${workflowId}/test-cases/synthesize`,
    { method: 'POST' },
  )
}

export function acceptTestCases(
  workflowId: string,
  session_ids: string[],
  label_overrides?: Record<string, string>,
) {
  return apiFetch<TestCaseAcceptResponse>(
    `/api/workflows/${workflowId}/test-cases/accept`,
    {
      method: 'POST',
      body: JSON.stringify({ session_ids, label_overrides }),
    },
  )
}

export interface ExpectedOutput {
  id: string
  type: 'expected_output'
  session_id?: string
  label?: string
  output_text?: string
  source?: string
}

export function getExpectedOutputs(workflowId: string) {
  return apiFetch<{ expected_outputs: ExpectedOutput[] }>(
    `/api/workflows/${workflowId}/expected-outputs`,
  )
}

export function deleteExpectedOutput(workflowId: string, expectedId: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/workflows/${workflowId}/expected-outputs/${expectedId}`,
    { method: 'DELETE' },
  )
}

// Quality history

export interface QualityHistoryRun {
  uuid: string
  score: number
  accuracy: number | null
  consistency: number | null
  grade: string | null
  model: string | null
  created_at: string
  num_checks: number
  checks_passed: number
  checks_failed: number
}

export interface RunHistoryEntry {
  id: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string
  tokens_input: number
  tokens_output: number
  documents_touched: number
  steps_completed?: number
  steps_total?: number
  session_id?: string
  result_snapshot: Record<string, unknown>
}

export function getWorkflowHistory(workflowId: string, limit = 50) {
  return apiFetch<{ runs: RunHistoryEntry[] }>(`/api/workflows/${workflowId}/history?limit=${limit}`)
}

export function getWorkflowQualityHistory(workflowId: string) {
  return apiFetch<{ runs: QualityHistoryRun[] }>(`/api/workflows/${workflowId}/quality-history`)
}

/** Phase 3 unified quality endpoint — mirrors getKBQuality. Returns the same
 *  shape so the shared QualityTimeline (Phase 4) can render any item_kind. */
export function getWorkflowQuality(workflowId: string) {
  return apiFetch<{
    history: QualityHistoryRun[]
    contract: Record<string, unknown>
  }>(`/api/workflows/${workflowId}/quality`)
}

export function getWorkflowImprovementSuggestions(workflowId: string) {
  return apiFetch<{ suggestions: string }>(`/api/workflows/${workflowId}/improvement-suggestions`, {
    method: 'POST',
  })
}

// Quality status

export interface WorkflowQualityStatus {
  status: 'validated' | 'unvalidated'
  score: number | null
  tier: string | null
  stale: boolean
  config_changed: boolean
  last_validated_at: string | null
}

export function getWorkflowQualityStatus(workflowId: string) {
  return apiFetch<WorkflowQualityStatus>(`/api/workflows/${workflowId}/quality-status`)
}


// ---------------------------------------------------------------------------
// Workflow Autovalidate (optimizer)
// ---------------------------------------------------------------------------

export type WorkflowOptimizationStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type WorkflowStepOverride = {
  model?: string
  prompt_variant?: string | null
}

export type WorkflowStepBreakdownEntry = {
  step: string
  score: number
  pass: number
  warn: number
  fail: number
  skip: number
  total: number
  evaluated: number
}

export type WorkflowOptimizationTrial = {
  trial_id: string
  config: {
    step_overrides: Record<string, WorkflowStepOverride>
  }
  score: number | null
  weighted_pass_rate: number | null
  lift_vs_default: number | null
  tokens_used: number
  status: 'completed' | 'early_stopped' | 'failed' | 'cancelled'
  duration_seconds: number | null
  step_breakdown: WorkflowStepBreakdownEntry[]
  error: string | null
  num_inputs_run: number
  num_inputs_total: number
}

export type WorkflowOptimizationSuggestion = {
  kind: 'weak_step' | 'redundant_workflow' | 'already_good' | string
  severity: 'info' | 'warning' | 'critical'
  message: string
  step?: string
}

export type WorkflowOptimizationRun = {
  uuid: string
  workflow_id: string
  status: WorkflowOptimizationStatus
  phase: string
  progress_message: string
  current_trial_index: number
  total_trials_planned: number
  best_score_so_far: number | null
  best_config_so_far: WorkflowOptimizationTrial['config'] | null
  token_budget: number
  tokens_used: number
  baseline_no_workflow_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  judge_variance: number | null
  judge_score_se: number | null
  judge_model: string | null
  winner_selection_reason: string | null
  tied_with_baseline: boolean
  best_config: WorkflowOptimizationTrial['config'] | null
  best_per_step_config: Record<string, WorkflowStepOverride>
  step_breakdown: WorkflowStepBreakdownEntry[]
  removed_steps: string[]
  trials: WorkflowOptimizationTrial[]
  suggestions: WorkflowOptimizationSuggestion[]
  previous_override: { step_overrides?: Record<string, WorkflowStepOverride> } | null
  /** Apply-preview rollup (Phase 2 loop closure). Per-STEP baseline-vs-winner
   *  score deltas — drives the Apply confirmation modal. */
  apply_preview?: ApplyPreview | null
  options: Record<string, unknown>
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  cancel_requested: boolean
}

export type ApplyPreviewItem = {
  item_id: string | null
  label: string | null
  baseline: number
  winner: number
  delta: number
  within_noise: boolean
  is_regression: boolean
  significant: boolean
}

export type ApplyPreview = {
  total: number
  will_change: number
  improvements: number
  regressions: number
  significant_regressions: number
  net_delta: number
  noise_sigma: number | null
  items: ApplyPreviewItem[]
}

export type WorkflowOptimizationRunSummary = {
  uuid: string
  workflow_id: string
  status: WorkflowOptimizationStatus
  started_at: string | null
  completed_at: string | null
  token_budget: number
  tokens_used: number
  baseline_no_workflow_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  judge_model: string | null
  num_trials: number
  best_config: WorkflowOptimizationTrial['config'] | null
  options: Record<string, unknown>
  error_message: string | null
}

export type StartWorkflowOptimizationOptions = {
  token_budget?: number
  max_candidates?: number
  apply_on_finish?: boolean
  include_judge?: boolean
}

export function startWorkflowOptimization(
  workflowId: string,
  opts: StartWorkflowOptimizationOptions = {},
) {
  return apiFetch<{ run_uuid: string; status: 'queued' }>(
    `/api/workflows/${workflowId}/optimize`,
    { method: 'POST', body: JSON.stringify(opts) },
  )
}

export function getActiveWorkflowOptimization(workflowId: string) {
  return apiFetch<{ run: WorkflowOptimizationRun | null }>(
    `/api/workflows/${workflowId}/optimize/active`,
  )
}

export function getWorkflowOptimization(workflowId: string, runUuid: string) {
  return apiFetch<WorkflowOptimizationRun>(
    `/api/workflows/${workflowId}/optimize/${runUuid}`,
  )
}

export function cancelWorkflowOptimization(workflowId: string, runUuid: string) {
  return apiFetch<{ ok: boolean; status: string; note?: string }>(
    `/api/workflows/${workflowId}/optimize/${runUuid}/cancel`,
    { method: 'POST' },
  )
}

/** Apply a workflow optimization. Pass ``stepIds`` for Phase 3 per-step
 *  subset apply (only those steps' winning overrides land); omit to apply
 *  every winning override at once (legacy behavior). */
export function applyWorkflowOptimization(
  workflowId: string,
  runUuid: string,
  stepIds?: string[],
) {
  return apiFetch<{
    ok: boolean
    applied_config: WorkflowOptimizationTrial['config']
    applied_step_ids: string[]
    partial: boolean
  }>(
    `/api/workflows/${workflowId}/optimize/${runUuid}/apply`,
    {
      method: 'POST',
      body: JSON.stringify(stepIds !== undefined ? { step_ids: stepIds } : {}),
    },
  )
}

export function revertWorkflowOptimization(workflowId: string, runUuid: string) {
  return apiFetch<{ ok: boolean; reverted_to: WorkflowOptimizationTrial['config'] | null }>(
    `/api/workflows/${workflowId}/optimize/${runUuid}/revert`,
    { method: 'POST' },
  )
}

export function listWorkflowOptimizationHistory(
  workflowId: string,
  options?: { limit?: number; skip?: number },
) {
  const params = new URLSearchParams()
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
  if (options?.skip !== undefined) params.set('skip', String(options.skip))
  const qs = params.toString()
  return apiFetch<{
    items: WorkflowOptimizationRunSummary[]
    skip: number
    limit: number
    count: number
  }>(`/api/workflows/${workflowId}/optimize${qs ? `?${qs}` : ''}`)
}
