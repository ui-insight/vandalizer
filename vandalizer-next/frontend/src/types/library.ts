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
  summary: string | null
  description: string | null
  category: string | null
  reviewer_user_id: string | null
  reviewer_notes: string | null
  submitted_at: string | null
  reviewed_at: string | null
}
