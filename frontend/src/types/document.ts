export interface Document {
  id: string
  title: string
  uuid: string
  extension: string
  processing: boolean
  valid: boolean
  validation_feedback?: string | null
  task_status: string | null
  folder: string | null
  created_at: string
  updated_at: string
  /** Size of the stored file; null when it is not on disk to measure. */
  size_bytes?: number | null
  token_count: number
  num_pages: number
  classification?: string | null
  classification_confidence?: number | null
  classified_at?: string | null
  classified_by?: string | null
  retention_hold?: boolean
  soft_deleted?: boolean
  /** 2+ once "Upload new version" has replaced an earlier copy of this file. */
  version_number?: number
  chromadb_ready?: boolean
  chunk_count?: number
  ingest_error?: string | null
  error_message?: string | null
  extraction_low_quality?: boolean
  /** Stored ingestion-warning codes: the text is real but not the whole
   * document, or the hidden-text safety check could not run. */
  ingestion_warnings?: string[]
  /** The codes as one readable clause, composed by the backend so the words
   * live in exactly one place. */
  ingestion_warning_text?: string
}

export interface Folder {
  id: string
  title: string
  uuid: string
  parent_id: string
  is_shared_team_root: boolean
  team_id?: string | null
  /** Files and folders directly inside, as this viewer would see them. */
  item_count?: number
  /** Derived: newest of the folder's creation and changes to what is in it. */
  updated_at?: string
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
  error_message: string | null
  /** False when the file itself is the problem (damaged, wrong format, gone)
   *  and a retry cannot help. Null/absent means a retry may help. */
  error_retryable?: boolean | null
  processing: boolean
  title: string
  extraction_low_quality?: boolean
  /** File extension without the dot ("pdf"), when known. */
  extension?: string | null
}
