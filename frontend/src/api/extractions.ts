import { apiFetch, ApiError } from './client'
import type { SearchSet, SearchSetItem } from '../types/workflow'

// SearchSet CRUD

export function createSearchSet(data: { title: string; space: string; set_type?: string; extraction_config?: Record<string, unknown> }) {
  return apiFetch<SearchSet>('/api/extractions/search-sets', {
    method: 'POST',
    body: JSON.stringify({ set_type: 'extraction', ...data }),
  })
}

export function listSearchSets(space?: string) {
  const params = space ? `?space=${encodeURIComponent(space)}` : ''
  return apiFetch<SearchSet[]>(`/api/extractions/search-sets${params}`)
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

// Run extraction

export function runExtractionSync(data: {
  search_set_uuid: string
  document_uuids: string[]
  model?: string
  extraction_config_override?: Record<string, unknown>
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
  extraction_config?: Record<string, unknown> | null
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

// Fillable PDF template upload

export async function uploadPdfTemplate(uuid: string, file: File): Promise<SearchSet> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api/extractions/search-sets/${uuid}/upload-template`, {
    method: 'POST',
    credentials: 'include',
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
  const res = await fetch(`/api/extractions/search-sets/${uuid}/generate-template`, {
    method: 'POST',
    credentials: 'include',
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
  const res = await fetch(`/api/extractions/search-sets/${uuid}/export-pdf`, {
    method: 'POST',
    credentials: 'include',
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
