export type LibraryScope = 'personal' | 'team' | 'verified'
export type LibraryItemKind = 'workflow' | 'search_set'

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
}

export interface LibraryFolder {
  uuid: string
  name: string
  parent_id: string | null
  scope: LibraryScope
}

export type VerificationStatus = 'draft' | 'submitted' | 'in_review' | 'approved' | 'rejected'

export interface VerificationRequest {
  id: string
  uuid: string
  item_kind: LibraryItemKind
  item_id: string
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
  updated_at?: string | null
  updated_by_user_id?: string | null
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
}

export interface VerifiedCollection {
  id: string
  title: string
  description: string | null
  promo_image_url: string | null
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
