export type LibraryScope = 'personal' | 'team' | 'verified'
export type LibraryItemKind = 'workflow' | 'search_set' | 'knowledge_base'

export interface Library {
  id: string
  scope: LibraryScope
  title: string
  description: string | null
  owner_user_id: string
  team_id: string | null
  item_count: number
  created_at: string | null
  updated_at: string | null
}

export interface LibraryItem {
  id: string
  item_id: string
  item_uuid: string | null
  kind: LibraryItemKind
  name: string
  description: string | null
  set_type: string | null
  tags: string[]
  note: string | null
  folder: string | null
  pinned: boolean
  favorited: boolean
  verified: boolean
  added_by_user_id: string
  created_at: string | null
  last_used_at: string | null
  quality_tier?: string | null
  quality_score?: number | null
  last_validated_at?: string | null
}

export interface LibraryFolder {
  uuid: string
  name: string
  parent_id: string | null
  scope: LibraryScope
  item_count: number
}

export type VerificationStatus = 'draft' | 'submitted' | 'in_review' | 'approved' | 'rejected' | 'returned'

export interface VerificationRequest {
  id: string
  uuid: string
  item_kind: LibraryItemKind
  item_id: string
  item_uuid?: string | null
  item_name?: string
  status: VerificationStatus
  submitter_user_id: string
  submitter_name: string | null
  submitter_org?: string | null
  submitter_role?: string | null
  summary: string | null
  description: string | null
  category: string | null
  item_version_hash?: string | null
  run_instructions?: string | null
  evaluation_notes?: string | null
  known_limitations?: string | null
  example_inputs?: string[]
  expected_outputs?: string[]
  dependencies?: string[]
  intended_use_tags?: string[]
  test_files?: { original_name: string; stored_name: string; path: string }[]
  validation_snapshot?: Record<string, unknown> | null
  validation_score?: number | null
  validation_tier?: string | null
  return_guidance?: string | null
  reviewer_user_id: string | null
  reviewer_notes: string | null
  submitted_at: string | null
  reviewed_at: string | null
}

export interface VerifiedItemMetadata {
  item_kind: string
  item_id: string
  display_name: string | null
  description: string | null
  markdown: string | null
  organization_ids: string[]
  updated_at?: string | null
  updated_by_user_id?: string | null
  quality_score?: number | null
  quality_tier?: string | null
  quality_grade?: string | null
  last_validated_at?: string | null
  validation_run_count?: number
}

export interface VerifiedCatalogItem {
  id: string
  item_id: string
  kind: LibraryItemKind
  name: string
  tags: string[]
  verified: boolean
  created_at: string | null
  display_name: string | null
  description: string | null
  markdown: string | null
  organization_ids: string[]
  quality_score: number | null
  quality_tier: string | null
  quality_grade: string | null
  last_validated_at: string | null
  validation_run_count: number
  // KB-specific fields
  total_sources?: number
  total_chunks?: number
  sources_ready?: number
  kb_status?: string
  source_uuid?: string  // the KB's uuid (for adopt/bookmark)
}

export interface VerifiedCollection {
  id: string
  title: string
  description: string | null
  promo_image_url: string | null
  featured: boolean
  item_ids: string[]
  created_by_user_id: string
  created_at: string
  updated_at: string
}

export interface ExaminerUser {
  user_id: string
  name: string | null
  email: string | null
  is_examiner: boolean
}

