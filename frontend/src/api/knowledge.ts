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

export function runKBValidation(uuid: string) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/validate`, {
    method: 'POST',
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

export function listKBTestQueries(uuid: string) {
  return apiFetch<{
    test_queries: {
      uuid: string
      query: string
      expected_source_labels: string[]
      expected_answer_contains: string | null
      created_at: string | null
    }[]
  }>(`/api/knowledge/${uuid}/test-queries`)
}

export function createKBTestQuery(uuid: string, data: {
  query: string
  expected_source_labels?: string[]
  expected_answer_contains?: string
}) {
  return apiFetch<Record<string, unknown>>(`/api/knowledge/${uuid}/test-queries`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteKBTestQuery(uuid: string, queryUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/test-queries/${queryUuid}`, {
    method: 'DELETE',
  })
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
