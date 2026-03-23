export type KBScope = 'mine' | 'team' | 'verified' | 'reference'

export interface KnowledgeBase {
  uuid: string
  title: string
  description: string
  status: 'empty' | 'building' | 'ready' | 'error'
  shared_with_team: boolean
  verified: boolean
  organization_ids: string[]
  team_id: string | null
  total_sources: number
  sources_ready: number
  sources_failed: number
  total_chunks: number
  created_at: string
  updated_at: string
  // Scope & ownership fields (from v2 list endpoint)
  user_id?: string
  scope?: KBScope
  is_reference?: boolean
  source_kb_uuid?: string
  reference_uuid?: string
}

export interface KnowledgeBaseSource {
  uuid: string
  source_type: 'document' | 'url'
  document_uuid?: string
  url?: string
  url_title?: string
  status: 'pending' | 'processing' | 'ready' | 'error'
  error_message?: string
  chunk_count: number
  created_at: string
}

export interface KnowledgeBaseDetail extends KnowledgeBase {
  sources: KnowledgeBaseSource[]
}

export interface KBListResponse {
  items: KnowledgeBase[]
  total: number
}

export interface KBReference {
  uuid: string
  source_kb_uuid: string
  user_id: string
  team_id?: string
  note?: string
  pinned: boolean
  created_at?: string
}
