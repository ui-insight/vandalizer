export interface Document {
  id: string
  title: string
  uuid: string
  extension: string
  processing: boolean
  valid: boolean
  task_status: string | null
  folder: string | null
  created_at: string
  token_count: number
  num_pages: number
}

export interface Folder {
  id: string
  title: string
  uuid: string
  parent_id: string
  is_shared_team_root: boolean
  team_id?: string | null
}

export interface ListContentsResponse {
  folders: Folder[]
  documents: Document[]
}

export interface PollStatusResponse {
  status: string | null
  status_messages: string[]
  complete: boolean
  raw_text: string
  validation_feedback: string | null
  valid: boolean
  path: string | null
}
