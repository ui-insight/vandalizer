import { apiFetch } from './client'
import type { KnowledgeBase, KnowledgeBaseDetail, KnowledgeBaseSourceDetail, KBListResponse, KBReference, KBScope } from '../types/knowledge'

export function listKnowledgeBases() {
  return apiFetch<KnowledgeBase[]>('/api/knowledge/list')
}

export function listKnowledgeBasesV2(params?: {
  scope?: KBScope
  search?: string
  skip?: number
  limit?: number
}) {
  const sp = new URLSearchParams()
  if (params?.scope) sp.set('scope', params.scope)
  if (params?.search) sp.set('search', params.search)
  if (params?.skip) sp.set('skip', String(params.skip))
  if (params?.limit) sp.set('limit', String(params.limit))
  const qs = sp.toString()
  return apiFetch<KBListResponse>(`/api/knowledge/list/v2${qs ? `?${qs}` : ''}`)
}

export function adoptKnowledgeBase(uuid: string, note?: string, teamId?: string) {
  return apiFetch<KBReference>(`/api/knowledge/${uuid}/adopt`, {
    method: 'POST',
    body: JSON.stringify({ note, team_id: teamId }),
  })
}

export function removeKBReference(refUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/reference/${refUuid}`, {
    method: 'DELETE',
  })
}

export function createKnowledgeBase(title: string, description?: string) {
  return apiFetch<KnowledgeBase>('/api/knowledge/create', {
    method: 'POST',
    body: JSON.stringify({ title, description }),
  })
}

export function getKnowledgeBase(uuid: string) {
  return apiFetch<KnowledgeBaseDetail>(`/api/knowledge/${uuid}`)
}

export function updateKnowledgeBase(uuid: string, data: { title?: string; description?: string; tags?: string[] }) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteKnowledgeBase(uuid: string, mode?: 'unshare_and_delete') {
  const qs = mode ? `?mode=${mode}` : ''
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}${qs}`, { method: 'DELETE' })
}

export function transferKnowledgeBaseToTeam(uuid: string) {
  return apiFetch<{ ok: boolean; team_owned: boolean }>(`/api/knowledge/${uuid}/transfer-to-team`, {
    method: 'POST',
  })
}

export function addDocumentsToKB(uuid: string, documentUuids: string[]) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_documents`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids }),
  })
}

export function addFolderToKB(uuid: string, folderUuid: string, includeSubfolders = true) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_folder`, {
    method: 'POST',
    body: JSON.stringify({ folder_uuid: folderUuid, include_subfolders: includeSubfolders }),
  })
}

export function convertDocumentsToKB(documentUuids: string[], title?: string) {
  return apiFetch<KnowledgeBase>('/api/knowledge/convert_documents', {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids, title }),
  })
}

export function addUrlsToKB(
  uuid: string,
  urls: string[],
  crawlEnabled = false,
  maxCrawlPages = 5,
  allowedDomains = '',
) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_urls`, {
    method: 'POST',
    body: JSON.stringify({
      urls,
      crawl_enabled: crawlEnabled,
      max_crawl_pages: maxCrawlPages,
      allowed_domains: allowedDomains,
    }),
  })
}

export function removeKBSource(uuid: string, sourceUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/source/${sourceUuid}`, {
    method: 'DELETE',
  })
}

export function getKBSource(uuid: string, sourceUuid: string) {
  return apiFetch<KnowledgeBaseSourceDetail>(`/api/knowledge/${uuid}/source/${sourceUuid}`)
}

export interface KBSourceResponse {
  uuid: string
  source_type: 'document' | 'url'
  document_uuid?: string | null
  document_title?: string | null
  url?: string | null
  url_title?: string | null
  custom_name?: string | null
  source_reference?: string | null
  status: 'pending' | 'processing' | 'ready' | 'error'
  error_message?: string | null
  chunk_count: number
  created_at?: string | null
}

/** Set or clear the user-provided label for a KB source. Pass `""` to clear. */
export function renameKBSource(uuid: string, sourceUuid: string, customName: string) {
  return apiFetch<KBSourceResponse>(`/api/knowledge/${uuid}/source/${sourceUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ custom_name: customName }),
  })
}

/** Set or clear the verifiable provenance ("Source: …") for a KB source. Pass `""` to clear. */
export function setKBSourceReference(uuid: string, sourceUuid: string, sourceReference: string) {
  return apiFetch<KBSourceResponse>(`/api/knowledge/${uuid}/source/${sourceUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ source_reference: sourceReference }),
  })
}

export function shareKnowledgeBase(uuid: string, comment?: string) {
  return apiFetch<{ ok: boolean; shared_with_team: boolean }>(`/api/knowledge/${uuid}/share`, {
    method: 'POST',
    body: JSON.stringify({ comment: comment || undefined }),
  })
}

export function submitKBForVerification(kbUuid: string, data: {
  summary?: string
  description?: string
  category?: string
}) {
  return apiFetch<Record<string, unknown>>('/api/verification/submit', {
    method: 'POST',
    body: JSON.stringify({
      item_kind: 'knowledge_base',
      item_id: kbUuid,
      ...data,
    }),
  })
}

export function setKBOrganizations(uuid: string, organizationIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify({ organization_ids: organizationIds }),
  })
}

export function getKBStatus(uuid: string) {
  return apiFetch<{
    uuid: string
    status: string
    total_sources: number
    sources_ready: number
    sources_failed: number
    total_chunks: number
    sources: { uuid: string; status: string; error_message: string; chunk_count: number }[]
  }>(`/api/knowledge/${uuid}/status`)
}

// Validation

export type KBValidationMode = 'judge' | 'judge+baseline'

export type KBJudgeVerdict = {
  score: number
  verdict: 'PASS' | 'FAIL' | 'WARN' | 'SKIPPED'
  confidence: number
  reasoning: string
  evidence: string
  missing_facts: string[]
  hallucinated_facts: string[]
}

export type KBValidationDetail = {
  query_uuid?: string
  query: string
  category?: string | null
  precision?: number
  retrieved_sources?: string[]
  expected_sources?: string[]
  answer_match?: boolean | null
  actual_answer?: string
  baseline_answer?: string | null
  judge?: KBJudgeVerdict | null
  baseline_judge?: KBJudgeVerdict | null
  lift?: number | null
  discrimination?: 'useful' | 'redundant' | 'failing' | 'other' | null
}

export type KBValidationResult = {
  kb_uuid: string
  kb_title: string
  raw_score: number
  num_test_queries: number
  num_sources: number
  mode?: KBValidationMode
  judge_model?: string | null
  source_health: {
    total: number
    healthy: number
    unhealthy: number
    ratio: number
    details: { uuid: string; name: string; status: string; error?: string }[]
  }
  chunk_coverage: {
    total: number
    with_chunks: number
    without_chunks: number
    ratio: number
    total_chunks: number
  }
  retrieval_precision: {
    total_queries: number
    avg_precision: number
    avg_judge_score?: number | null
    avg_baseline_score?: number | null
    avg_lift?: number | null
    num_queries_judged?: number
    num_queries_baselined?: number
    judge_variance?: number | null
    judge_variance_meta?: { sigma: number | null; n: number; sampled_query_uuids: string[] } | null
    discrimination_summary?: { useful: number; redundant: number; failing: number; other: number }
    details: KBValidationDetail[]
  }
  // Certified quality score (raw_score after the low-sample-size discount),
  // matching the persisted quality tile shown later.
  score?: number | null
  quality_tier?: string | null
  score_breakdown?: {
    raw_score: number
    final_score: number
    sample_size_factor: number
    sample_size_penalty: number
    num_test_cases: number
    num_runs: number
    test_cases_needed: number
    runs_needed: number
  } | null
}

export function runKBValidation(
  uuid: string,
  options?: { mode?: KBValidationMode; skip_judge?: boolean },
) {
  return apiFetch<KBValidationResult>(`/api/knowledge/${uuid}/validate`, {
    method: 'POST',
    body: JSON.stringify(options ?? {}),
  })
}

export function runKBValidationAsync(
  uuid: string,
  options?: { mode?: KBValidationMode; skip_judge?: boolean },
) {
  return apiFetch<{ task_id: string; status: 'queued' }>(`/api/knowledge/${uuid}/validate`, {
    method: 'POST',
    body: JSON.stringify({ ...(options ?? {}), async: true }),
  })
}

export function getKBSourceHealth(uuid: string) {
  return apiFetch<{
    total: number
    healthy: number
    unhealthy: number
    ratio: number
    details: { uuid: string; source_type: string; name: string; status: string; error?: string }[]
  }>(`/api/knowledge/${uuid}/source-health`)
}

export function getKBQuality(uuid: string) {
  return apiFetch<{
    history: Record<string, unknown>[]
    contract: Record<string, unknown>
  }>(`/api/knowledge/${uuid}/quality`)
}

export type KBFeedbackImpact = {
  /** ISO timestamp of the most recent ``applied_at`` on a winning run. Null
   * when no optimization has been applied to this KB yet (no before/after split). */
  applied_at: string | null
  /** 0..1 thumbs-up rate over chat answers grounded in this KB BEFORE apply. */
  thumbs_up_rate_before: number | null
  /** 0..1 thumbs-up rate AFTER apply. */
  thumbs_up_rate_after: number | null
  n_before: number
  n_after: number
  /** Overall thumbs-up rate (used pre-apply when there's no before/after to split). */
  thumbs_up_rate_overall: number | null
  n_overall: number
}

export function getKBFeedbackImpact(uuid: string) {
  return apiFetch<KBFeedbackImpact>(`/api/knowledge/${uuid}/feedback-impact`)
}

// Test queries

export type KBTestQuery = {
  uuid: string
  query: string
  expected_source_labels: string[]
  expected_answer_contains: string | null
  expected_answer: string | null
  category: string | null
  auto_generated: boolean
  source_chunk_ids: string[]
  last_judged_score: number | null
  last_judged_at: string | null
  created_at: string | null
  updated_at: string | null
}

export function listKBTestQueries(uuid: string) {
  return apiFetch<{ test_queries: KBTestQuery[] }>(
    `/api/knowledge/${uuid}/test-queries`,
  )
}

export function createKBTestQuery(uuid: string, data: {
  query: string
  expected_source_labels?: string[]
  expected_answer_contains?: string
  expected_answer?: string
  category?: string
}) {
  return apiFetch<KBTestQuery>(`/api/knowledge/${uuid}/test-queries`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateKBTestQuery(uuid: string, queryUuid: string, data: {
  query?: string
  expected_source_labels?: string[]
  expected_answer_contains?: string | null
  expected_answer?: string | null
  category?: string | null
}) {
  return apiFetch<KBTestQuery>(`/api/knowledge/${uuid}/test-queries/${queryUuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteKBTestQuery(uuid: string, queryUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/test-queries/${queryUuid}`, {
    method: 'DELETE',
  })
}

export function generateKBTestQueries(
  uuid: string,
  options?: { coverage?: 'quick' | 'standard' | 'exhaustive'; async?: boolean },
) {
  return apiFetch<
    | { created: number; test_queries: KBTestQuery[] }
    | { task_id: string; status: 'queued' }
  >(`/api/knowledge/${uuid}/test-queries/generate`, {
    method: 'POST',
    body: JSON.stringify(options ?? {}),
  })
}

// ---------------------------------------------------------------------------
// KB Autovalidate (optimizer)
// ---------------------------------------------------------------------------

export type OptimizationStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type OptimizationCoverage = 'quick' | 'standard' | 'exhaustive'

export type PerQueryResult = {
  query_uuid: string
  query: string
  category?: string | null
  score: number
  verdict?: 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED' | null
  confidence?: number | null
  reasoning?: string
  missing_facts?: string[]
  hallucinated_facts?: string[]
  actual_answer?: string
  retrieved_sources?: string[]
}

export type TrialConfig = {
  k: number
  model: string | null
  prompt_variant: string
  query_rewriting: boolean
  source_label_visibility: boolean
  // LLM reranking sweep axis (backend RERANK_VALUES). Older runs may omit it;
  // the backend default is 'off'.
  rerank?: string
  // Answer-generation temperature sweep axis (backend ANSWER_TEMPERATURE_VALUES).
  // Older runs may omit it; the backend default is 0.0.
  answer_temperature?: number
}

export type OptimizationTrial = {
  trial_id: string
  config: TrialConfig
  // Blended quality score (judge 0.40 + retrieval 0.25 + health 0.20 + coverage 0.15)
  // on the same 0..1 scale the validation header reports.
  score: number
  // Raw judge mean for this trial — kept separately so lift CI and cross-judge
  // audit operate on judge units (the blended score's variance is dominated by
  // the judge component since retrieval/health/coverage are config-invariant).
  judge_score?: number | null
  lift_vs_default: number | null
  num_queries_judged?: number
  discrimination_summary?: { useful: number; redundant: number; failing: number; other: number } | null
  per_query_results?: PerQueryResult[]
  tokens_used: number
  status: 'completed' | 'early_stopped' | 'failed'
  error?: string
  started_at?: string
  duration_seconds?: number
  // Why an early_stopped trial bailed: 'below_no_kb' (worse than no knowledge
  // base at all) or 'below_best' (trailing the current leader). Present only on
  // early_stopped trials.
  early_stop_reason?: 'below_no_kb' | 'below_best'
}

export type TestQuerySnapshot = {
  total: number
  query_uuids: string[]
  expected_answer_hashes: Record<string, string>
  auto_generated_count: number
  user_authored_count: number
  categories: Record<string, number>
  sources_covered: string[]
  total_sources: number
}

export type JudgeVarianceMeta = {
  sigma: number | null
  n: number
  sampled_query_uuids: string[]
}

export type LiftCI = {
  lift: number
  lower: number
  upper: number
  p_value: number
  n_queries: number
  n_iterations: number
  method: 'paired_bootstrap'
  confidence_level: number
}

export type CrossJudge = {
  model: string
  score: number
  delta: number
  tokens_used: number
}

export type OptimizationSuggestion = {
  kind: 'low_lift_baseline' | 'coverage_gap' | 'saturated' | 'retrieval_bottleneck' | string
  severity: 'info' | 'warning' | 'critical'
  message: string
  source_uuid?: string
}

export type KBOptimizationRun = {
  uuid: string
  kb_uuid: string
  status: OptimizationStatus
  phase: string
  progress_message: string
  current_trial_index: number
  total_trials_planned: number
  best_score_so_far: number | null
  best_config_so_far: OptimizationTrial['config'] | null
  token_budget: number
  tokens_used: number
  estimated_cost_usd: number | null
  actual_cost_usd: number | null
  // All "score" fields below are on the blended quality scale (judge 40% +
  // retrieval 25% + health 20% + coverage 15%) — same as the validation header.
  // Exception: baseline_no_kb_score is raw judge (no KB → nothing to blend).
  baseline_no_kb_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  // Config-invariant components cached once per run; surfacing them lets the UI
  // show "blended = judge × 0.40 + invariants × 0.60" breakdowns.
  baseline_retrieval_score?: number | null
  baseline_health_score?: number | null
  baseline_coverage_score?: number | null
  // Raw default-config judge score (pre-blending) — used by per-query lift CI
  // displays that need to stay in judge units.
  baseline_default_judge_score?: number | null
  judge_variance: number | null
  judge_model: string | null
  // Snapshot of the default RAGConfig (incl. any live override) used to compute
  // baseline_default_score. Surfaced so BestConfigCard can render a diff vs winner.
  default_config?: OptimizationTrial['config'] | null
  best_config: OptimizationTrial['config'] | null
  trials: OptimizationTrial[]
  default_per_query_results?: PerQueryResult[]
  no_kb_per_query_results?: PerQueryResult[]
  rng_seed?: number | null
  judge_prompt_version?: string | null
  judge_temperature?: number | null
  test_query_snapshot?: TestQuerySnapshot | null
  judge_variance_meta?: JudgeVarianceMeta | null
  lift_ci?: LiftCI | null
  cross_judge?: CrossJudge | null
  optimized_score_train?: number | null
  holdout_default_score?: number | null
  train_query_uuids?: string[]
  holdout_query_uuids?: string[]
  overfitting_warning?: boolean
  stopped_reason?: string | null
  data_source_suggestions: OptimizationSuggestion[]
  options: Record<string, unknown>
  error_message: string | null
  // Structured failure code for actionable banner remediation. Stable codes
  // mirror the backend (kb_not_found, test_set_too_small, judge_unavailable,
  // baselines_failed, budget_exhausted, unknown). Older runs without
  // classification leave this null and the banner falls back to error_message.
  error_code?: string | null
  error_context?: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  // Server-computed elapsed seconds (started_at → completed_at|now). Drives the
  // live timer skew-free; the client ticks forward from this base. Optional so
  // older payloads fall back to the started_at delta.
  elapsed_seconds?: number | null
  cancel_requested: boolean
  // Apply/revert lifecycle (Phase 1 loop closure).
  previous_override?: OptimizationTrial['config'] | null
  applied_at?: string | null
  reverted_at?: string | null
  tied_with_baseline?: boolean
  // Apply-preview rollup (Phase 2 loop closure).
  apply_preview?: ApplyPreview | null
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

/** How the tuning run's evaluation set is assembled in the Test-set wizard step:
 * reuse the KB's saved questions, generate a fresh set, or combine both. */
export type TestSetBuildMode = 'existing' | 'generate' | 'combined'

export type StartOptimizationOptions = {
  token_budget: number
  include_indexing_track?: boolean
  apply_on_finish?: boolean
  autogen_coverage?: OptimizationCoverage
  test_set_build_mode?: TestSetBuildMode
  /** The exact reviewed test-question UUIDs to grade against — authoritative
   * when present so "generate only" / "combine" scope the run precisely. */
  test_query_uuids?: string[]
}

export function startKBOptimization(uuid: string, opts: StartOptimizationOptions) {
  return apiFetch<{ run_uuid: string; status: 'queued' }>(`/api/knowledge/${uuid}/optimize`, {
    method: 'POST',
    body: JSON.stringify(opts),
  })
}

export function getActiveKBOptimization(uuid: string) {
  return apiFetch<{ run: KBOptimizationRun | null }>(`/api/knowledge/${uuid}/optimize/active`)
}

export function getKBOptimization(uuid: string, runUuid: string) {
  return apiFetch<KBOptimizationRun>(`/api/knowledge/${uuid}/optimize/${runUuid}`)
}

export function cancelKBOptimization(uuid: string, runUuid: string) {
  return apiFetch<{ ok: boolean; status: string; note?: string }>(
    `/api/knowledge/${uuid}/optimize/${runUuid}/cancel`,
    { method: 'POST' },
  )
}

export function applyKBOptimization(uuid: string, runUuid: string) {
  return apiFetch<{
    ok: boolean
    applied_config: OptimizationTrial['config']
    previous_override: OptimizationTrial['config'] | null
    applied_at: string
  }>(
    `/api/knowledge/${uuid}/optimize/${runUuid}/apply`,
    { method: 'POST' },
  )
}

export function revertKBOptimization(uuid: string, runUuid: string) {
  return apiFetch<{
    ok: boolean
    restored_config: OptimizationTrial['config'] | null
    reverted_at: string
  }>(
    `/api/knowledge/${uuid}/optimize/${runUuid}/revert`,
    { method: 'POST' },
  )
}

export type KBBaselineProbeResult = {
  no_kb_score: number | null
  num_queries_judged: number
  sample_query_ids: string[]
  tokens_used: number
  duration_ms: number
}

/** Cheap pre-flight: run no-KB judge on a small sample of test queries so the
 * tuning wizard can show the user the floor before committing a budget. */
export function getKBBaselineProbe(
  uuid: string,
  opts?: { sample_size?: number; query_uuids?: string[] },
) {
  return apiFetch<KBBaselineProbeResult>(`/api/knowledge/${uuid}/baseline-probe`, {
    method: 'POST',
    body: JSON.stringify(opts ?? {}),
  })
}

export type KBOptimizationRunSummary = {
  uuid: string
  kb_uuid: string
  status: OptimizationStatus
  started_at: string | null
  completed_at: string | null
  token_budget: number
  tokens_used: number
  baseline_no_kb_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  judge_model: string | null
  num_trials: number
  best_config: OptimizationTrial['config'] | null
  options: Record<string, unknown>
  error_message: string | null
  eval_set_size?: number | null
  judge_prompt_version?: string | null
  lift_ci?: LiftCI | null
}

export function listKBOptimizationHistory(
  uuid: string,
  options?: { limit?: number; skip?: number },
) {
  const params = new URLSearchParams()
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
  if (options?.skip !== undefined) params.set('skip', String(options.skip))
  const qs = params.toString()
  return apiFetch<{
    items: KBOptimizationRunSummary[]
    skip: number
    limit: number
    count: number
  }>(`/api/knowledge/${uuid}/optimize${qs ? `?${qs}` : ''}`)
}

// Cost estimate helper. Uses System Config's per-model `cost_per_1m_input` /
// `cost_per_1m_output` if available. Falls back to tokens-only display when
// the cost fields aren't populated. The caller passes the available models
// and the chosen budget; this returns a string the modal can render.
export function formatBudgetEstimate(
  tokens: number,
  modelEntry?: { cost_per_1m_input?: number | null; cost_per_1m_output?: number | null } | null,
): { tokens_label: string; cost_label: string | null } {
  const tokens_label = tokens >= 1_000_000
    ? `≈${(tokens / 1_000_000).toFixed(1)}M tokens`
    : tokens >= 1_000
    ? `≈${(tokens / 1_000).toFixed(0)}k tokens`
    : `≈${tokens} tokens`

  if (!modelEntry) return { tokens_label, cost_label: null }
  const inputRate = modelEntry.cost_per_1m_input
  const outputRate = modelEntry.cost_per_1m_output
  if (typeof inputRate !== 'number' || typeof outputRate !== 'number') {
    return { tokens_label, cost_label: null }
  }
  // Assume ~70/30 input/output split for RAG + judge calls.
  const dollars = (tokens / 1_000_000) * (inputRate * 0.7 + outputRate * 0.3)
  // Round up conservatively so we don't undersell cost.
  const rounded = Math.ceil(dollars * 100) / 100
  return { tokens_label, cost_label: `≈$${rounded.toFixed(2)}` }
}

// Clone

export function cloneKnowledgeBase(uuid: string, title?: string) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/clone`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

// Export / Import

export interface KBExportPayload {
  format_version: number
  exported_at?: string | null
  title: string
  description?: string | null
  sources: {
    source_type: 'document' | 'url'
    document_uuid?: string | null
    document_title?: string | null
    url?: string | null
    url_title?: string | null
    custom_name?: string | null
    content?: string | null
    crawl_enabled?: boolean
    max_crawl_pages?: number
    parent_source_uuid?: string | null
    crawled_urls?: string[] | null
  }[]
}

/** Fetch an export payload for a knowledge base. Caller can serialize and save it. */
export async function fetchKBExport(uuid: string): Promise<KBExportPayload> {
  return apiFetch<KBExportPayload>(`/api/knowledge/${uuid}/export`)
}

/** Download a knowledge base as a .kb.json file in the browser. */
export async function downloadKBExport(uuid: string, fallbackTitle = 'knowledge_base'): Promise<void> {
  const payload = await fetchKBExport(uuid)
  const title = payload.title || fallbackTitle
  const safeTitle = title.replace(/[^A-Za-z0-9_.-]+/g, '_').replace(/^_+|_+$/g, '') || 'knowledge_base'
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeTitle}.kb.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function importKnowledgeBase(payload: KBExportPayload, title?: string) {
  return apiFetch<{ uuid: string; title: string; imported_sources: number }>(
    '/api/knowledge/import',
    {
      method: 'POST',
      body: JSON.stringify({ payload, title }),
      // Importing may involve many re-embed calls; allow more time.
      timeoutMs: 300_000,
    },
  )
}

// Suggestions

export function submitKBSuggestion(uuid: string, data: {
  suggestion_type: string
  url?: string
  document_uuid?: string
  note?: string
}) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/suggestions`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listKBSuggestions(uuid: string) {
  return apiFetch<{
    suggestions: {
      uuid: string
      suggestion_type: string
      url: string | null
      document_uuid: string | null
      note: string | null
      status: string
      suggested_by_name: string | null
      suggested_by_user_id: string
      reviewed_by_user_id: string | null
      reviewed_at: string | null
      created_at: string | null
    }[]
  }>(`/api/knowledge/${uuid}/suggestions`)
}

export function reviewKBSuggestion(kbUuid: string, suggestionUuid: string, accept: boolean) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${kbUuid}/suggestions/${suggestionUuid}`, {
    method: 'PATCH',
    body: JSON.stringify({ accept }),
  })
}
