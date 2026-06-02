import { apiFetch, ApiError, rawFetch } from './client'
import type { SearchSet, SearchSetItem } from '../types/workflow'

// SearchSet CRUD

export function createSearchSet(data: { title: string; set_type?: string; extraction_config?: Record<string, unknown> }) {
  return apiFetch<SearchSet>('/api/extractions/search-sets', {
    method: 'POST',
    body: JSON.stringify({ set_type: 'extraction', ...data }),
  })
}

export function listSearchSets(params?: { scope?: string; search?: string }) {
  const sp = new URLSearchParams()
  if (params?.scope) sp.set('scope', params.scope)
  if (params?.search) sp.set('search', params.search)
  const qs = sp.toString()
  return apiFetch<SearchSet[]>(`/api/extractions/search-sets${qs ? `?${qs}` : ''}`)
}

export function getSearchSet(uuid: string) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}`)
}

export function updateSearchSet(uuid: string, data: { title?: string; extraction_config?: Record<string, unknown> }) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteSearchSet(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/search-sets/${uuid}`, { method: 'DELETE' })
}

export function cloneSearchSet(uuid: string) {
  return apiFetch<SearchSet>(`/api/extractions/search-sets/${uuid}/clone`, { method: 'POST' })
}

// Items

export function addItem(searchSetUuid: string, data: { searchphrase: string; searchtype?: string; title?: string; is_optional?: boolean; enum_values?: string[] }) {
  return apiFetch<SearchSetItem>(`/api/extractions/search-sets/${searchSetUuid}/items`, {
    method: 'POST',
    body: JSON.stringify({ searchtype: 'extraction', ...data }),
  })
}

export function listItems(searchSetUuid: string) {
  return apiFetch<SearchSetItem[]>(`/api/extractions/search-sets/${searchSetUuid}/items`)
}

export function updateItem(itemId: string, data: { searchphrase?: string; title?: string; is_optional?: boolean; enum_values?: string[] }) {
  return apiFetch<SearchSetItem>(`/api/extractions/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteItem(itemId: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/items/${itemId}`, { method: 'DELETE' })
}

// Reorder items

export function reorderItems(searchSetUuid: string, itemIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/search-sets/${searchSetUuid}/reorder-items`, {
    method: 'POST',
    body: JSON.stringify({ item_ids: itemIds }),
  })
}

// Build from document (AI field generation)

export function buildFromDocument(searchSetUuid: string, documentUuids: string[], model?: string) {
  return apiFetch<{ entities: string[] }>(`/api/extractions/search-sets/${searchSetUuid}/build-from-document`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids, model }),
  })
}

// AI-suggest extraction fields from documents without persisting to a SearchSet.
// Used by the workflow editor's manual-fields path.

export function suggestFields(documentUuids: string[], model?: string) {
  return apiFetch<{ entities: string[] }>(`/api/extractions/suggest-fields`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids, model }),
  })
}

// Run extraction

export function runExtractionSync(data: {
  search_set_uuid: string
  document_uuids: string[]
  model?: string
  extraction_config_override?: Record<string, unknown>
  combined_context?: boolean
}, signal?: AbortSignal) {
  return apiFetch<{ results: unknown[] }>('/api/extractions/run-sync', {
    method: 'POST',
    body: JSON.stringify(data),
    signal,
  })
}

// Test cases

export interface TestCase {
  id: string
  uuid: string
  search_set_uuid: string
  label: string
  source_type: string
  source_text?: string | null
  document_uuid?: string | null
  document_exists?: boolean | null
  expected_values: Record<string, string>
  user_id: string
  created_at: string
}

export interface FieldValidationResult {
  field_name: string
  expected: string | null
  extracted_values: (string | null)[]
  most_common_value: string | null
  consistency: number
  accuracy: number | null
  accuracy_method: string | null
  enum_compliance: number | null
}

export interface TestCaseValidationResult {
  test_case_uuid: string
  label: string
  fields: FieldValidationResult[]
  overall_accuracy: number | null
  overall_consistency: number
}

export interface ValidationResult {
  search_set_uuid: string
  num_runs: number
  test_cases: TestCaseValidationResult[]
  aggregate_accuracy: number | null
  aggregate_consistency: number
}

export function createTestCase(data: {
  search_set_uuid: string
  label: string
  source_type: string
  source_text?: string
  document_uuid?: string
  expected_values: Record<string, string>
}) {
  return apiFetch<TestCase>('/api/extractions/test-cases', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listTestCases(searchSetUuid: string) {
  return apiFetch<TestCase[]>(`/api/extractions/test-cases?search_set_uuid=${encodeURIComponent(searchSetUuid)}`)
}

export function updateTestCase(uuid: string, data: {
  label?: string
  source_type?: string
  source_text?: string
  document_uuid?: string
  expected_values?: Record<string, string>
}) {
  return apiFetch<TestCase>(`/api/extractions/test-cases/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteTestCase(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/extractions/test-cases/${uuid}`, { method: 'DELETE' })
}

export function runValidation(data: {
  search_set_uuid: string
  test_case_uuids?: string[]
  num_runs?: number
  model?: string
}) {
  return apiFetch<ValidationResult>('/api/extractions/validate', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// V2 Validation (source-based)

export interface ValidationSource {
  source_type: 'document' | 'text'
  document_uuid?: string
  label?: string
  source_text?: string
  expected_values: Record<string, string>
}

export interface ExecutiveSummary {
  mean_accuracy: number | null
  mean_consistency: number
  perfect_fields_count: number
  total_fields_count: number
  run_to_run_std_dev: number
  best_run: { source_index: number; run_index: number; correct: number }
  worst_run: { source_index: number; run_index: number; correct: number }
  per_run_reproducibility: { source_label: string; runs: number[] }[]
}

export interface SourceFieldResult {
  field_name: string
  expected: string | null
  extracted_values: (string | null)[]
  most_common_value: string | null
  distinct_value_count: number
  consistency: number
  accuracy: number | null
  accuracy_method: string | null
  enum_compliance: number | null
  error_types: Record<string, number>
}

export interface SourceValidationResult {
  source_label: string
  source_type: string
  fields: SourceFieldResult[]
  overall_accuracy: number | null
  overall_consistency: number
  per_run_correct: number[]
}

export interface ChallengingField {
  field_name: string
  source_label: string
  accuracy: number | null
  consistency: number
  most_common_error: string
}

export interface ValidationV2Result {
  search_set_uuid: string
  num_runs: number
  num_sources: number
  executive_summary: ExecutiveSummary
  sources: SourceValidationResult[]
  aggregate_accuracy: number | null
  aggregate_consistency: number
  challenging_fields: ChallengingField[]
  error_type_summary: Record<string, number>
  cross_field_score?: number | null
  cross_field_summary?: CrossFieldSummary | null
  cross_field_results?: CrossFieldRuleResult[]
}

export function runValidationV2(data: {
  search_set_uuid: string
  sources: ValidationSource[]
  num_runs?: number
  model?: string
}) {
  return apiFetch<ValidationV2Result>('/api/extractions/validate-v2', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Quality history

export interface ScoreBreakdown {
  raw_score: number
  final_score: number
  sample_size_factor: number
  sample_size_penalty: number
  num_test_cases: number
  num_runs: number
  test_cases_needed: number
  runs_needed: number
}

export interface QualityHistoryRun {
  uuid: string
  score: number
  accuracy: number | null
  consistency: number | null
  grade: string | null
  model: string | null
  created_at: string
  num_test_cases: number
  num_runs?: number
  score_breakdown?: ScoreBreakdown | null
  extraction_config?: Record<string, unknown> | null
}

export interface ExtractionRunHistoryEntry {
  id: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string
  tokens_input: number
  tokens_output: number
  documents_touched: number
  result_snapshot: Record<string, unknown>
}

export function getExtractionHistory(uuid: string, limit = 50) {
  return apiFetch<{ runs: ExtractionRunHistoryEntry[] }>(`/api/extractions/search-sets/${uuid}/history?limit=${limit}`)
}

export function getExtractionQualityHistory(uuid: string) {
  return apiFetch<{ runs: QualityHistoryRun[] }>(`/api/extractions/search-sets/${uuid}/quality-history`)
}

export interface SparklinePoint {
  score: number
  created_at: string
}

export function getQualitySparkline(uuid: string, limit = 10) {
  return apiFetch<{ scores: SparklinePoint[] }>(`/api/extractions/search-sets/${uuid}/quality-sparkline?limit=${limit}`)
}

export interface QualityStatus {
  status: 'validated' | 'unvalidated'
  score: number | null
  tier: string | null
  last_validated_at?: string | null
  config_changed: boolean
  stale: boolean
}

export function getQualityStatus(uuid: string) {
  return apiFetch<QualityStatus>(`/api/extractions/search-sets/${uuid}/quality-status`)
}

export interface QualityContractStatus {
  status: string
  tier: string | null
  score: number | null
  last_validated_at: string | null
  is_stale: boolean
  has_alerts: boolean
  monitored: boolean
}

export function getQualityContract(uuid: string) {
  return apiFetch<QualityContractStatus>(`/api/extractions/search-sets/${uuid}/quality-contract`)
}

export function getExtractionImprovementSuggestions(uuid: string) {
  return apiFetch<{ suggestions: string }>(`/api/extractions/search-sets/${uuid}/improvement-suggestions`, {
    method: 'POST',
  })
}

export interface TuningResult {
  label: string
  model: string
  config_override: Record<string, unknown>
  accuracy: number
  consistency: number
  score: number
  elapsed_seconds: number
  error?: string
}

export interface FindBestSettingsResult {
  best: TuningResult
  results: TuningResult[]
  recommendation: string
  search_set_uuid: string
}

export async function findBestSettingsStream(
  uuid: string,
  numRuns = 2,
  maxCandidates = 8,
  onEvent: (event: TuningStreamEvent) => void,
) {
  const res = await rawFetch(`/api/extractions/search-sets/${uuid}/find-best-settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num_runs: numRuns, max_candidates: maxCandidates }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed (${res.status})`)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch { /* skip malformed */ }
      }
    }
  }
}

export type TuningStreamEvent =
  | { kind: 'start'; total: number; candidates: string[] }
  | { kind: 'testing'; index: number; label: string; total: number }
  | { kind: 'result'; index: number; result: TuningResult; total: number }
  | { kind: 'done'; best: TuningResult; results: TuningResult[]; recommendation: string }
  | { kind: 'error'; detail: string }

// Tuning result persistence

export function getTuningResult(uuid: string) {
  return apiFetch<{ tuning_result: FindBestSettingsResult & { ran_at: string } | null }>(
    `/api/extractions/search-sets/${uuid}/tuning-result`
  )
}

export function clearTuningResult(uuid: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/extractions/search-sets/${uuid}/tuning-result`,
    { method: 'DELETE' }
  )
}

// ---------------------------------------------------------------------------
// Extraction optimization (Autovalidate parallel to KB Autovalidate)
// ---------------------------------------------------------------------------

export type ExtractionOptimizationStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface ExtractionTrial {
  trial_id: string
  config: Record<string, unknown> & { model?: string | null }
  score: number | null
  accuracy: number | null
  consistency: number | null
  lift_vs_default: number | null
  tokens_used: number
  status: 'completed' | 'failed' | 'early_stopped' | string
  duration_seconds?: number
  error?: string
  /** Cross-field rule outcome for this trial. Null when no rules are
   *  configured on the SearchSet. Shape matches CrossFieldSummary. */
  cross_field_summary?: CrossFieldSummary | null
}

export interface OptimizationCrossFieldRuleRow {
  rule_id: string
  type?: string | null
  label?: string | null
  pass: number
  fail: number
  unparseable: number
  pass_rate: number | null
}

export interface PostApplyValidation {
  accuracy: number | null
  consistency: number | null
  cross_field_pass_rate?: number | null
  score?: number | null
  ran_at: string
  test_case_count: number
  source: 'apply_on_finish' | 'explicit_apply'
}

export interface ExtractionOptimizationRun {
  uuid: string
  search_set_uuid: string
  status: ExtractionOptimizationStatus
  phase: string
  progress_message: string
  current_trial_index: number
  total_trials_planned: number
  best_score_so_far: number | null
  best_config_so_far: Record<string, unknown> | null
  token_budget: number
  tokens_used: number
  estimated_cost_usd: number | null
  actual_cost_usd: number | null
  baseline_no_tool_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  /** Per-item LLM-judge nondeterminism (sample stddev of replay - original deltas). */
  judge_variance: number | null
  /** σ / √N_items — the standard error on the per-trial mean score. The
   *  significance gate compares trial-score deltas to 2 × this value. */
  judge_score_se: number | null
  /** True when no trial beat the user's current config by more than 2 × SE.
   *  Suppresses apply_on_finish — surface as "no significant improvement". */
  tied_with_baseline: boolean
  /** Reason tag from variance-aware winner selection. One of:
   *  highest_score, default_in_cluster, closest_to_default,
   *  tied_with_baseline_no_default_in_cluster, no_judge_variance. */
  winner_selection_reason: string | null
  /** Candidate models excluded from the sweep because they share a family
   *  with the judge_model (self-preference guard). */
  excluded_models: string[]
  judge_model: string | null
  best_config: Record<string, unknown> | null
  trials: ExtractionTrial[]
  field_breakdown: Array<{ field: string; accuracy: number; consistency: number }>
  /** Cross-field rule outcome on the winning config. Null when no rules. */
  winner_cross_field_summary?: CrossFieldSummary | null
  /** Per-rule pass/fail breakdown on the winning config (worst-first). */
  winner_cross_field_rule_breakdown?: OptimizationCrossFieldRuleRow[]
  /** Snapshot of the validation run executed after the winning config was
   *  applied — drives the "the optimizer's lift held up on a real run" delta
   *  shown on the completed panel. Null until apply runs. */
  post_apply_validation?: PostApplyValidation | null
  suggestions: Array<{
    severity: 'info' | 'warning' | 'critical'
    message: string
    kind?: string
    rule_id?: string
    rule_type?: string
    field?: string
  }>
  previous_override: Record<string, unknown> | null
  /** Apply-preview rollup (Phase 2 loop closure). Per-FIELD baseline-vs-winner
   *  accuracy deltas — drives the Apply confirmation modal. */
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

export interface StartExtractionOptimizationOptions {
  token_budget?: number     // 0 = use max_candidates directly (Phase 1A default)
  max_candidates?: number   // default 8 on backend
  apply_on_finish?: boolean
  /** Phase 1B: when true, use semantic LLM judge instead of strict-match scoring. */
  include_judge?: boolean
  /** Wizard checkbox selection — only these test cases participate in the run.
   *  Omitted/empty means tune against every test case for the set. */
  test_case_uuids?: string[]
}

/** Cheap no-settings baseline probe used by the tuning wizard. Mirrors KB's
 * `/baseline-probe` — runs extraction with `config_override={}` against a
 * sample of judgeable test cases, judged by the user's model. */
export interface ExtractionBaselineProbeResult {
  no_settings_score: number | null
  num_cases_judged: number
  sample_case_ids: string[]
  tokens_used: number
  duration_ms: number
}

export function getExtractionBaselineProbe(
  uuid: string,
  opts: { case_uuids?: string[]; sample_size?: number } = {},
) {
  return apiFetch<ExtractionBaselineProbeResult>(
    `/api/extractions/search-sets/${uuid}/baseline-probe`,
    {
      method: 'POST',
      body: JSON.stringify({
        sample_size: opts.sample_size ?? 5,
        case_uuids: opts.case_uuids ?? null,
      }),
    },
  )
}

export function startExtractionOptimization(uuid: string, opts: StartExtractionOptimizationOptions = {}) {
  return apiFetch<{ run_uuid: string; status: 'queued' }>(
    `/api/extractions/search-sets/${uuid}/optimize`,
    {
      method: 'POST',
      body: JSON.stringify({
        token_budget: opts.token_budget ?? 0,
        max_candidates: opts.max_candidates ?? 8,
        apply_on_finish: opts.apply_on_finish ?? false,
        include_judge: opts.include_judge ?? false,
        ...(opts.test_case_uuids && opts.test_case_uuids.length
          ? { test_case_uuids: opts.test_case_uuids }
          : {}),
      }),
    }
  )
}

export function getActiveExtractionOptimization(uuid: string) {
  return apiFetch<{ run: ExtractionOptimizationRun | null }>(
    `/api/extractions/search-sets/${uuid}/optimize/active`
  )
}

export function getExtractionOptimization(uuid: string, runUuid: string) {
  return apiFetch<ExtractionOptimizationRun>(
    `/api/extractions/search-sets/${uuid}/optimize/${runUuid}`
  )
}

export function cancelExtractionOptimization(uuid: string, runUuid: string) {
  return apiFetch<{ ok: boolean; status: string; note?: string }>(
    `/api/extractions/search-sets/${uuid}/optimize/${runUuid}/cancel`,
    { method: 'POST' }
  )
}

export function applyExtractionOptimization(uuid: string, runUuid: string) {
  return apiFetch<{ ok: boolean; applied_config: Record<string, unknown> }>(
    `/api/extractions/search-sets/${uuid}/optimize/${runUuid}/apply`,
    { method: 'POST' }
  )
}

// History of past optimization runs (newest first)

export interface ExtractionOptimizationRunSummary {
  uuid: string
  search_set_uuid: string
  status: ExtractionOptimizationStatus
  started_at: string | null
  completed_at: string | null
  token_budget: number
  tokens_used: number
  baseline_no_tool_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  judge_model: string | null
  num_trials: number
  best_config: Record<string, unknown> | null
  options: Record<string, unknown>
  error_message: string | null
}

export function listExtractionOptimizationHistory(
  uuid: string,
  options?: { limit?: number; skip?: number },
) {
  const params = new URLSearchParams()
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
  if (options?.skip !== undefined) params.set('skip', String(options.skip))
  const qs = params.toString()
  return apiFetch<{
    items: ExtractionOptimizationRunSummary[]
    skip: number
    limit: number
    count: number
  }>(`/api/extractions/search-sets/${uuid}/optimize${qs ? `?${qs}` : ''}`)
}

// Test-case auto-generator (Phase 1B)
// Two-step flow: generate proposals → user reviews → approves.

export type TestCaseCoverage = 'quick' | 'standard' | 'exhaustive'

export interface ProposedTestCase {
  proposal_id: string
  label: string
  source_type: 'document' | 'text'
  document_uuid?: string | null
  source_text?: string | null
  expected_values: Record<string, string>
  auto_generated: boolean
}

export interface GenerateTestCasesResult {
  proposals: ProposedTestCase[]
  errors: Array<{ document_uuid: string; reason: string }>
}

export function generateTestCaseProposals(
  uuid: string,
  documentUuids: string[],
  coverage: TestCaseCoverage = 'standard',
) {
  return apiFetch<GenerateTestCasesResult>(
    `/api/extractions/search-sets/${uuid}/generate-test-cases`,
    {
      method: 'POST',
      body: JSON.stringify({ document_uuids: documentUuids, coverage }),
    },
  )
}

export function approveTestCaseProposals(uuid: string, proposals: ProposedTestCase[]) {
  return apiFetch<{
    count: number
    test_cases: Array<{
      uuid: string
      label: string
      source_type: string
      document_uuid: string | null
      expected_values: Record<string, string>
    }>
  }>(
    `/api/extractions/search-sets/${uuid}/test-cases/approve-bulk`,
    {
      method: 'POST',
      body: JSON.stringify({ proposals }),
    },
  )
}

// Direct apply/revert (without an optimization run — also used when the
// user accepts a recommended config from elsewhere).
export function applyExtractionConfig(uuid: string, config: Record<string, unknown>) {
  return apiFetch<{ ok: boolean; applied_at: string; previous_override: Record<string, unknown> | null }>(
    `/api/extractions/search-sets/${uuid}/apply-config`,
    {
      method: 'POST',
      body: JSON.stringify({ config }),
    }
  )
}

export function revertExtractionConfig(uuid: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/extractions/search-sets/${uuid}/revert-config`,
    { method: 'POST' }
  )
}

// Export / Import

export function exportSearchSetUrl(uuid: string) {
  return `/api/extractions/search-sets/${uuid}/export`
}

export async function downloadValidationZip(uuid: string): Promise<void> {
  const res = await rawFetch(`/api/extractions/search-sets/${uuid}/download-validation`, {
    method: 'GET',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Download failed' }))
    throw new ApiError(res.status, body.detail || 'Download failed')
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : `validation-${uuid}.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function importSearchSet(file: File, targetUuid?: string): Promise<SearchSet> {
  const form = new FormData()
  form.append('file', file)
  if (targetUuid) form.append('target_uuid', targetUuid)
  const res = await rawFetch('/api/extractions/search-sets/import', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Import failed' }))
    throw new ApiError(res.status, body.detail || 'Import failed')
  }
  return res.json()
}

// Fillable PDF template upload

export async function uploadPdfTemplate(uuid: string, file: File): Promise<SearchSet> {
  const form = new FormData()
  form.append('file', file)
  const res = await rawFetch(`/api/extractions/search-sets/${uuid}/upload-template`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new ApiError(res.status, body.detail || 'Upload failed')
  }
  return res.json()
}

// Generate example fillable PDF template from current extraction items

export async function generateExampleTemplate(uuid: string): Promise<void> {
  const res = await rawFetch(`/api/extractions/search-sets/${uuid}/generate-template`, {
    method: 'POST',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Generation failed' }))
    throw new ApiError(res.status, body.detail || 'Generation failed')
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : 'template.pdf'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Export extraction results as PDF (filled template or report)

export async function exportExtractionPdf(
  uuid: string,
  results: Record<string, string>,
  documentNames: string[],
): Promise<void> {
  const res = await rawFetch(`/api/extractions/search-sets/${uuid}/export-pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results, document_names: documentNames }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Export failed' }))
    throw new ApiError(res.status, body.detail || 'Export failed')
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename="([^"]+)"/)
  const filename = match ? match[1] : 'extraction.pdf'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Cross-field validation rules
// ---------------------------------------------------------------------------

export type CrossFieldRuleType =
  | 'sum_equals'
  | 'conditional_required'
  | 'range_check'
  | 'cross_reference'
  | 'date_order'
  | 'custom_expression'

export interface CrossFieldRule {
  id?: string
  type: CrossFieldRuleType
  enabled?: boolean
  auto_disabled?: boolean
  auto_disabled_reason?: string | null
  eval_count?: number
  pass_count?: number
  fail_count?: number
  fp_count?: number
  source?: 'user' | 'suggested' | 'imported'
  // type-specific params
  source_fields?: string[]
  target_field?: string
  tolerance?: number
  condition_field?: string
  condition_value?: string
  required_field?: string
  field?: string
  min?: number | null
  max?: number | null
  field_a?: string
  field_b?: string
  match_type?: 'contains' | 'equals'
  expression?: string
}

export interface CrossFieldRuleResult {
  rule: CrossFieldRule
  rule_id?: string
  status: 'pass' | 'fail' | 'unparseable'
  passed: boolean
  message: string
  test_case_uuid?: string
  test_case_label?: string
  source_label?: string
}

export interface CrossFieldSummary {
  pass: number
  fail: number
  unparseable: number
  violation_rate: number
  pass_rate: number | null
  total: number
}

export function getCrossFieldRules(uuid: string) {
  return apiFetch<{ rules: CrossFieldRule[] }>(
    `/api/extractions/search-sets/${uuid}/cross-field-rules`
  )
}

export function updateCrossFieldRules(uuid: string, rules: CrossFieldRule[]) {
  return apiFetch<{ rules: CrossFieldRule[] }>(
    `/api/extractions/search-sets/${uuid}/cross-field-rules`,
    {
      method: 'PUT',
      body: JSON.stringify({ rules }),
    }
  )
}

export function suggestCrossFieldRules(uuid: string) {
  return apiFetch<{ suggestions: CrossFieldRule[] }>(
    `/api/extractions/search-sets/${uuid}/cross-field-rules/suggest`,
    { method: 'POST' }
  )
}

export function markRuleFalsePositive(uuid: string, ruleId: string) {
  return apiFetch<{ rule: CrossFieldRule }>(
    `/api/extractions/search-sets/${uuid}/cross-field-rules/${ruleId}/mark-false-positive`,
    { method: 'POST' }
  )
}
