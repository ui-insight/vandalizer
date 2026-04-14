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

export interface Workflow {
  id: string;
  uuid: string;
  name: string;
  description: string | null;
  user_id: string;
  num_executions: number;
  steps: WorkflowStep[];
  input_config?: { trigger_type?: string };
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
  approval_request_id: string | null;
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
}

export interface UserConfig {
  model: string;
  temperature: number;
  top_p: number;
  available_models: ModelInfo[];
}
