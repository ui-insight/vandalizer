export interface ChatMessage {
  /** Local stream interruption; does not claim cancellation of server work. */
  interruption?: 'stopped' | 'connection'
  role: 'system' | 'user' | 'assistant'
  content: string
  thinking?: string
  thinking_duration?: number
  tool_calls?: ToolCallInfo[]
  tool_results?: ToolResultInfo[]
  segments?: StreamSegment[]
  citations?: Citation[]
  /** KB and attached-document answers: dollar amounts / percentages in the
   *  answer that no source states — likely recalled from the model's memory. */
  unsupported_figures?: string[]
  /** Sentences that read a gap in the sources as a rule, e.g. "may be any length" (#1012). */
  silence_inferences?: string[]
  /** KB answers only: sources the answer cites for text they don't contain —
   *  e.g. a scraped page holding only its title. */
  unsupported_citations?: string[]
  /** Documents in scope when this turn was asked — `{uuid, title}` each, with
   *  a final `{truncated: n}` when the selection was larger than is recorded.
   *  Present on user turns; assistant turns carry `citations` instead. */
  source_documents?: SourceDocument[]
  /** Snapshot of the outgoing request, recorded locally for live turns. */
  request_scope?: { documents: string[]; folders: string[]; knowledgeBases: string[]; project?: string }
}

/** A document that was attached when a question was asked. The title is stored
 *  with the uuid so the record stays readable after the document is deleted. */
export interface SourceDocument {
  uuid?: string
  title?: string
  /** How many further documents were in scope but not recorded. */
  truncated?: number
}

export interface ToolCallInfo {
  tool_name: string
  tool_call_id: string
  args: Record<string, unknown>
}

export interface QualityMeta {
  score: number | null
  tier: string | null
  grade: string | null
  accuracy?: number | null
  consistency?: number | null
  last_validated_at: string | null
  num_test_cases?: number | null
  num_runs?: number | null
  active_alerts?: Array<{ type: string; severity: string; message: string }>
  // Latest autovalidate (optimizer) run for the item, if any.
  optimization?: {
    status: string
    run_uuid: string
    optimized_score?: number | null
    baseline_score?: number | null
    tied_with_baseline?: boolean
    applied_at?: string | null
    completed_at?: string | null
    pending_recommendation?: boolean
  } | null
  // Workflows only: the saved validation plan no longer matches the
  // workflow definition (regenerate before trusting validation results).
  plan_stale?: boolean | null
}

export interface ToolResultInfo {
  tool_name: string
  tool_call_id: string
  content: unknown
  quality: QualityMeta | null
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
  /** Runs only: the chat that started this run, when a chat tool did. */
  source_conversation_id?: string | null
  /** Runs only: titles of the first documents the run read. */
  document_titles?: string[]
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

export type StreamSegment =
  | { kind: 'text'; content: string }
  | { kind: 'tool_call'; call: ToolCallInfo }
  | { kind: 'tool_result'; result: ToolResultInfo }
  // A message the user sent mid-turn, consumed at that point in the run.
  | { kind: 'queued_user'; content: string }

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

// Backend-computed context meter (chat_service Phase 2): honest estimate of
// the request being sent plus the warn/compact/block escalation ladder.
// Prefer this over any frontend-derived ratio — the backend knows the real
// window, the response reserve, and the provider-reported usage anchor.
export interface ContextMeterInfo {
  estimated_tokens: number
  context_window: number
  effective_window: number
  warn_threshold: number
  compact_threshold: number
  block_threshold: number
  state: 'ok' | 'warning' | 'compact' | 'blocked'
  percent_until_compact: number
  estimate_source: 'usage_anchor' | 'token_count'
  /** Tokens the conversation's earlier messages account for. Absent from
   *  older servers. When attached files fill most of the window, trimming the
   *  conversation won't help, so the "getting long" nudge stays hidden. */
  history_tokens?: number | null
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
  /** Set on chips made from a page number the model wrote about an attached
   *  document (#998): whether the sentence citing it was found on that page.
   *  Only 'found' is shown as an ordinary source; absent on KB and web chips,
   *  which come from retrieval rather than the model. */
  grounding?: 'found' | 'not_found' | 'unchecked'
  // User-verifiable provenance for the KB source (origin URL / citation).
  source_reference?: string | null
  // Set when the KB source is a URL — citation chip links out to it.
  url?: string | null
  /** The snippet's number in its turn's prompt; the answer cites it as [S#]. */
  ref?: number
  /** What [S#] reads as: the same text as `label` on answers that carry one;
   *  "PAPPG.pdf, p. ~54" or the bare source name on older ones. */
  cite_label?: string
  /** The passage's source line, built the way a workflow run's is:
   *  "PAPPG.pdf · p. 54", "budget.xlsx · Sheet1", or — for a source without
   *  pages, such as an eCFR subpart or a policy web page — where the passage
   *  sits: "Subpart E · § 200.423", "APM 45.13 Program Income · part 3".
   *  Never names the knowledge base (`kb_title` does). Absent on answers
   *  saved before chat sent it; those rebuild the line from title and page. */
  label?: string | null
  /** The passage itself (up to 5,000 characters), for the source preview.
   *  Older answers carry only `content_preview`. */
  content?: string | null
  /** Whether the answer cited this snippet. false = retrieved and searched
   *  but not used. Absent on answers saved before the distinction, which
   *  show every snippet as a source. */
  used?: boolean
}

// Live task checklist from the update_plan tool (chat_tools Phase 8).
export interface PlanTask {
  content: string
  active_form: string
  status: 'pending' | 'in_progress' | 'completed'
}

export interface StreamChunk {
  kind:
    | 'text'
    | 'thinking'
    | 'thinking_done'
    | 'error'
    | 'tool_call'
    | 'tool_result'
    | 'usage'
    | 'context_budget'
    | 'context_meter'
    | 'context_notice'
    | 'compaction'
    | 'plan_update'
    | 'queue_consumed'
    | 'sources'
    | 'sources_used'
    | 'grounding_warning'
  content: string
  duration?: number
  tool_name?: string
  tool_call_id?: string
  args?: Record<string, unknown>
  quality?: QualityMeta | null
  request_tokens?: number
  response_tokens?: number
  total_tokens?: number
  plan?: ContextBudgetPlan
  meter?: ContextMeterInfo
  /** context_budget only: a larger model that would hold this request, when
   *  one exists and passes the server's privacy rule. Absent means there is
   *  nothing to offer — the dialog must not invent a choice. */
  suggested_model?: SuggestedModel | null
  action?: string
  tokens_dropped?: number
  // compaction kind only: auto-compaction lifecycle for this turn.
  status?: 'started' | 'done' | 'failed'
  // plan_update kind only: the full current checklist. Named plan_tasks
  // because `plan` is already the context_budget chunk's ContextBudgetPlan.
  plan_tasks?: PlanTask[]
  // Error-only: machine-readable failure code + optional suggested recovery.
  code?: string
  suggested_action?: 'convert_to_kb' | 'continue'
  oversize_documents?: OversizeDocument[]
  // sources kind only: citation list emitted before the LLM streams text.
  sources?: Citation[]
  // sources_used only: the [S#] numbers the finished answer cited.
  used_refs?: number[]
  // grounding_warning only: figures in the finished answer no snippet states.
  unsupported_figures?: string[]
  /** Sentences that read a gap in the sources as a rule, e.g. "may be any length" (#1012). */
  silence_inferences?: string[]
  // grounding_warning only: cited sources that don't contain the cited text.
  unsupported_citations?: string[]
}

export interface SuggestedModel {
  name: string
  tag: string
  context_window: number
}
