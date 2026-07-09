export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
  thinking?: string
  thinking_duration?: number
  tool_calls?: ToolCallInfo[]
  tool_results?: ToolResultInfo[]
  segments?: StreamSegment[]
  citations?: Citation[]
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
}

export interface Citation {
  document_id?: string | null
  document_title: string
  page?: number | null
  sheet?: string | null
  chunk_id?: string | null
  score?: number | null
  content_preview?: string
  // User-verifiable provenance for the KB source (origin URL / citation).
  source_reference?: string | null
  // Set when the KB source is a URL — citation chip links out to it.
  url?: string | null
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
}
