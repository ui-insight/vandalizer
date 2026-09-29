export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
  thinking?: string
  thinking_duration?: number
  citations?: Citation[]
  /** KB answers only: dollar amounts / percentages in the answer that no
   *  retrieved snippet states — likely recalled from the model's memory. */
  unsupported_figures?: string[]
  /** Documents in scope when this turn was asked — `{uuid, title}` each, with
   *  a final `{truncated: n}` when the selection was larger than is recorded.
   *  Present on user turns; assistant turns carry `citations` instead. */
  source_documents?: SourceDocument[]
}

/** A document that was attached when a question was asked. The title is stored
 *  with the uuid so the record stays readable after the document is deleted. */
export interface SourceDocument {
  uuid?: string
  title?: string
  /** How many further documents were in scope but not recorded. */
  truncated?: number
}

export interface FileAttachment {
  id: string
  filename: string
  file_type: string
  content_preview?: string
  content_length?: number
  created_at: string
}

export interface UrlAttachment {
  id: string
  url: string
  title: string
  created_at: string
}

export interface ChatConversation {
  uuid: string
  title: string
  messages: ChatMessage[]
  url_attachments: UrlAttachment[]
  file_attachments: FileAttachment[]
}

export interface ActivityEvent {
  id: string
  type: 'conversation' | 'search_set_run' | 'workflow_run'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled'
  title: string | null
  conversation_id: string | null
  search_set_uuid: string | null
  workflow_id: string | null
  workflow_session_id: string | null
  started_at: string | null
  finished_at: string | null
  last_updated_at: string | null
  error: string
  tokens_input: number
  tokens_output: number
  message_count: number
  result_snapshot: Record<string, unknown>
  meta_summary?: Record<string, unknown>
}

export interface ContextBudgetPlan {
  model: string
  context_window: number
  response_reserve: number
  input_budget: number
  total_input_tokens: number
  system_tokens: number
  user_message_tokens: number
  history_tokens: number
  documents_tokens: number
  attachments_tokens: number
  headroom_tokens: number
}

export interface OversizeDocument {
  uuid: string
  title: string
  token_count: number
}

export interface Citation {
  document_id?: string | null
  /** SmartDocument uuid behind this source, when one exists and is still
   *  readable. Absent for URL-backed sources and deleted documents — those
   *  stay preview-only because there is nothing to open. */
  document_uuid?: string | null
  document_title: string
  page?: number | null
  /** Last page of a chunk that crosses page breaks, when the cited passage
   *  could not be pinned to one page; rendered as "p. 2–3". */
  page_end?: number | null
  /** Page was interpolated from OCR text, not measured. See #603. */
  page_approximate?: boolean
  sheet?: string | null
  /** Which knowledge base this snippet came from. Only set when several are
   *  attached to the chat, where the filename alone doesn't say. */
  kb_title?: string | null
  kb_uuid?: string | null
  chunk_id?: string | null
  score?: number | null
  content_preview?: string
}

export interface StreamChunk {
  kind:
    | 'text'
    | 'thinking'
    | 'thinking_done'
    | 'error'
    | 'usage'
    | 'context_budget'
    | 'context_notice'
    | 'sources'
    | 'grounding_warning'
  content: string
  duration?: number
  request_tokens?: number
  response_tokens?: number
  total_tokens?: number
  plan?: ContextBudgetPlan
  /** context_budget only: a larger model that would hold this request, when
   *  one exists and passes the server's privacy rule. Absent means there is
   *  nothing to offer — the dialog must not invent a choice. */
  suggested_model?: SuggestedModel | null
  action?: string
  tokens_dropped?: number
  // Error-only: machine-readable failure code + optional suggested recovery.
  code?: string
  suggested_action?: 'convert_to_kb'
  oversize_documents?: OversizeDocument[]
  // sources kind only: citation list emitted before the LLM streams text.
  sources?: Citation[]
  // grounding_warning only: figures in the finished answer no snippet states.
  unsupported_figures?: string[]
}

export interface SuggestedModel {
  name: string
  tag: string
  context_window: number
}
