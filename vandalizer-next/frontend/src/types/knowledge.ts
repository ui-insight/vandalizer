export interface KnowledgeBase {
  uuid: string
  title: string
  description: string
  status: 'empty' | 'building' | 'ready' | 'error'
  shared_with_team: boolean
  verified: boolean
  group_ids: string[]
  team_id: string | null
  total_sources: number
  sources_ready: number
  sources_failed: number
  total_chunks: number
  created_at: string
  updated_at: string
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
