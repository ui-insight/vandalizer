export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
  thinking?: string
  thinking_duration?: number
  tool_calls?: ToolCallInfo[]
  tool_results?: ToolResultInfo[]
  segments?: StreamSegment[]
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
  error: string
  tokens_input: number
  tokens_output: number
  message_count: number
  result_snapshot: Record<string, unknown>
}

export type StreamSegment =
  | { kind: 'text'; content: string }
  | { kind: 'tool_call'; call: ToolCallInfo }
  | { kind: 'tool_result'; result: ToolResultInfo }

export interface StreamChunk {
  kind: 'text' | 'thinking' | 'thinking_done' | 'error' | 'tool_call' | 'tool_result' | 'usage'
  content: string
  duration?: number
  tool_name?: string
  tool_call_id?: string
  args?: Record<string, unknown>
  quality?: QualityMeta | null
  request_tokens?: number
  response_tokens?: number
  total_tokens?: number
}
