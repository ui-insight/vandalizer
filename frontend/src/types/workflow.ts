export interface SearchSetItem {
  id: string;
  searchphrase: string;
  searchset: string | null;
  searchtype: string;
  title: string | null;
  is_optional: boolean;
  enum_values: string[];
  pdf_binding?: string | null;
}

export interface ValidationPortability {
  test_case_count: number;
  text_count: number;
  document_count: number;
  missing_snapshot_count: number;
}

export interface SearchSet {
  id: string;
  title: string;
  uuid: string;
  status: string;
  set_type: string;
  user_id: string | null;
  team_id: string | null;
  is_global: boolean;
  verified: boolean;
  item_count: number;
  extraction_config: Record<string, unknown>;
  fillable_pdf_url?: string | null;
  quality_score?: number | null;
  quality_tier?: string | null;
  last_validated_at?: string | null;
  validation_run_count?: number;
  validation_portability?: ValidationPortability | null;
}

export interface WorkflowTask {
  id: string;
  name: string;
  data: Record<string, unknown>;
}

export interface WorkflowStep {
  id: string;
  name: string;
  data: Record<string, unknown>;
  is_output: boolean;
  tasks: WorkflowTask[];
}

export interface AuthorRef {
  user_id: string;
  name: string | null;
  email: string | null;
}

export interface SaveOutputConfig {
  enabled?: boolean;
  destination_folder?: string;
  format?: 'markdown' | 'csv' | 'json' | 'pdf' | 'text';
  file_naming?: string;
  on_rerun?: 'new' | 'overwrite';
  skip_semantic_ingestion?: boolean;
}

export interface Workflow {
  id: string;
  uuid: string;
  name: string;
  description: string | null;
  user_id: string;
  // Set when the workflow is shared with a team; null for personal workflows.
  // Used to decide whether the "Remove from team" action is offered.
  team_id?: string | null;
  num_executions: number;
  steps: WorkflowStep[];
  input_config?: { trigger_type?: string };
  output_config?: { storage?: SaveOutputConfig; [key: string]: unknown };
  can_manage?: boolean;
  created_by?: AuthorRef | null;
}

export interface WorkflowErrorPayload {
  code: string;
  suggested_action?: 'convert_to_kb';
  oversize_documents?: Array<{ uuid: string; title: string; token_count: number }>;
}

export interface WorkflowCitation {
  document_id?: string | null;
  document_title: string;
  page?: number | null;
  sheet?: string | null;
  chunk_id?: string | null;
  score?: number | null;
  similarity?: number | null;
  content_preview?: string;
}

export interface WorkflowStatus {
  status: string;
  num_steps_completed: number;
  num_steps_total: number;
  current_step_name: string | null;
  current_step_detail: string | null;
  current_step_preview: string | null;
  final_output: unknown;
  steps_output: Record<string, unknown> | null;
  output_step_names: string[];
  approval_request_id: string | null;
  error?: string | null;
  error_payload?: WorkflowErrorPayload | null;
  retrieved_sources?: WorkflowCitation[];
}

export interface ModelInfo {
  name: string;
  tag: string;
  external: boolean;
  thinking: boolean;
  speed: string;
  tier: string;
  privacy: string;
  supports_structured: boolean;
  multimodal: boolean;
  supports_pdf: boolean;
  context_window: number;
  // USD per 1M tokens (optional). Populated for paid external models so the
  // KB Autovalidate budget modal can show dollar estimates next to tokens.
  cost_per_1m_input?: number | null;
  cost_per_1m_output?: number | null;
}

export interface UserConfig {
  model: string;
  temperature: number;
  top_p: number;
  available_models: ModelInfo[];
}
