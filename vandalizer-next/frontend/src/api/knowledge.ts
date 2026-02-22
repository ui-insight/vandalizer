import { apiFetch } from './client'
import type { KnowledgeBase, KnowledgeBaseDetail } from '../types/knowledge'

export function listKnowledgeBases() {
  return apiFetch<KnowledgeBase[]>('/api/knowledge/list')
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
  return apiFetch<Record<string, unknown>>('/api/verify/submit', {
    method: 'POST',
    body: JSON.stringify({
      item_kind: 'knowledge_base',
      item_id: kbUuid,
      ...data,
    }),
  })
}

export function setKBGroups(uuid: string, groupIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/knowledge/${uuid}/update`, {
    method: 'POST',
    body: JSON.stringify({ group_ids: groupIds }),
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
