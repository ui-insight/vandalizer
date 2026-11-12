import { apiFetch } from './client'

export interface PageTemplate { uuid: string; name: string; description: string; owner_name: string; team_id: string | null; can_manage: boolean; created_at: string }
export interface TemplateSource { artifact_uuid?: string; revision?: string; preview_id?: string }
export interface TemplateDraft { draft_id: string; preview_html: string; fields: { id: string; label: string; bar: boolean }[] }
export interface TemplateCheck { filled: number; missing: number; retained: number; source_title: string; template_name: string }
const path = (uuid: string) => `/api/page-templates/${encodeURIComponent(uuid)}`
export const browsePageTemplates = (search = '', page = 1) => apiFetch<{ items: PageTemplate[]; total: number; page: number; page_size: number }>(`/api/page-templates?${new URLSearchParams({ search, page: String(page) })}`)
export const preparePageTemplate = (source: TemplateSource) => apiFetch<TemplateDraft>('/api/page-templates/prepare', { method: 'POST', body: JSON.stringify(source) })
export const savePageTemplate = (body: { draft_id: string; name: string; description: string; guidance: string; field_labels: Record<string, string> }) => apiFetch<PageTemplate>('/api/page-templates', { method: 'POST', body: JSON.stringify(body) })
export const pageTemplateContentUrl = (uuid: string) => `${path(uuid)}/content`
export const sharePageTemplate = (uuid: string, teamId: string | null) => apiFetch(`${path(uuid)}/team`, { method: 'PUT', body: JSON.stringify({ team_id: teamId }) })
export const deletePageTemplate = (uuid: string) => apiFetch(path(uuid), { method: 'DELETE' })

export function readTemplateCheck(value: unknown): TemplateCheck | undefined {
  if (!value || typeof value !== 'object') return undefined
  const v = value as Record<string, unknown>
  if (typeof v.source_title !== 'string' || typeof v.template_name !== 'string' || ![v.filled, v.missing, v.retained].every(n => typeof n === 'number' && Number.isInteger(n) && n >= 0)) return undefined
  return v as unknown as TemplateCheck
}
