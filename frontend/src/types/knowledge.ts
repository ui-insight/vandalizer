export type KBScope = 'mine' | 'team' | 'verified' | 'reference'

export interface KnowledgeBase {
  uuid: string
  title: string
  description: string
  status: 'empty' | 'building' | 'ready' | 'error'
  shared_with_team: boolean
  team_owned: boolean
  verified: boolean
  organization_ids: string[]
  tags: string[]
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
  // Set by KB Autovalidate's apply path
  has_optimized_config?: boolean
  optimized_config_set_at?: string | null
  // AI-trust signals from the latest validation run. Scores are 0-1.
  last_validation_score?: number | null
  last_validation_baseline_score?: number | null
  last_validation_lift?: number | null
  last_validated_at?: string | null
  // Per-requesting-user: when this user last chatted with the KB (ISO string).
  last_used_at?: string | null
}

export interface KnowledgeBaseSource {
  uuid: string
  source_type: 'document' | 'url'
  document_uuid?: string
  document_title?: string
  url?: string
  url_title?: string
  custom_name?: string | null
  source_reference?: string | null
  status: 'pending' | 'processing' | 'ready' | 'error'
  error_message?: string
  chunk_count: number
  created_at: string
}

export interface KnowledgeBaseSourceDetail extends KnowledgeBaseSource {
  content?: string | null
  crawl_enabled: boolean
  max_crawl_pages: number
  parent_source_uuid?: string | null
  crawled_urls?: string[] | null
  child_sources: KnowledgeBaseSource[]
  processed_at?: string | null
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
