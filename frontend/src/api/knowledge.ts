import { apiFetch } from './client'
import type { KnowledgeBase, KnowledgeBaseDetail, KBListResponse, KBReference, KBScope } from '../types/knowledge'

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

export function updateKnowledgeBase(uuid: string, data: { title?: string; description?: string }) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteKnowledgeBase(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}`, { method: 'DELETE' })
}

export function addDocumentsToKB(uuid: string, documentUuids: string[]) {
  return apiFetch<{ ok: boolean; added: number }>(`/api/knowledge/${uuid}/add_documents`, {
    method: 'POST',
    body: JSON.stringify({ document_uuids: documentUuids }),
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

export function shareKnowledgeBase(uuid: string) {
  return apiFetch<{ ok: boolean; shared_with_team: boolean }>(`/api/knowledge/${uuid}/share`, {
    method: 'POST',
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
    discrimination_summary?: { useful: number; redundant: number; failing: number; other: number }
    details: KBValidationDetail[]
  }
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

export type OptimizationTrial = {
  trial_id: string
  config: {
    k: number
    model: string | null
    prompt_variant: string
    query_rewriting: boolean
    source_label_visibility: boolean
  }
  score: number
  lift_vs_default: number | null
  num_queries_judged?: number
  discrimination_summary?: { useful: number; redundant: number; failing: number; other: number } | null
  tokens_used: number
  status: 'completed' | 'early_stopped' | 'failed'
  error?: string
  started_at?: string
  duration_seconds?: number
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
  baseline_no_kb_score: number | null
  baseline_default_score: number | null
  optimized_score: number | null
  judge_variance: number | null
  judge_model: string | null
  best_config: OptimizationTrial['config'] | null
  trials: OptimizationTrial[]
  data_source_suggestions: OptimizationSuggestion[]
  options: Record<string, unknown>
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  cancel_requested: boolean
}

export type StartOptimizationOptions = {
  token_budget: number
  include_indexing_track?: boolean
  apply_on_finish?: boolean
  autogen_coverage?: OptimizationCoverage
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
  return apiFetch<{ ok: boolean; applied_config: OptimizationTrial['config'] }>(
    `/api/knowledge/${uuid}/optimize/${runUuid}/apply`,
    { method: 'POST' },
  )
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
  modelEntry?: { cost_per_1m_input?: number; cost_per_1m_output?: number } | null,
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
