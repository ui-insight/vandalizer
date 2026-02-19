export interface SearchSetItem {
  id: string;
  searchphrase: string;
  searchset: string | null;
  searchtype: string;
  title: string | null;
}

export interface SearchSet {
  id: string;
  title: string;
  uuid: string;
  space: string;
  status: string;
  set_type: string;
  user_id: string | null;
  is_global: boolean;
  verified: boolean;
  item_count: number;
  extraction_config: Record<string, unknown>;
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
  name: string;
  description: string | null;
  user_id: string;
  space: string | null;
  num_executions: number;
  steps: WorkflowStep[];
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
}

export interface ModelInfo {
  name: string;
  tag: string;
  external: boolean;
  thinking: boolean;
}

export interface UserConfig {
  model: string;
  temperature: number;
  top_p: number;
  available_models: ModelInfo[];
}
