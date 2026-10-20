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
  /** Monitoring found a regression here and nobody has reviewed it yet. */
  regression_pending_review?: boolean;
  last_validated_at?: string | null;
  validation_run_count?: number;
  validation_portability?: ValidationPortability | null;
  // Whether the current user may manage (edit/validate) this set. Returned by
  // the backend SearchSetResponse; absent on older payloads, so treat as true.
  can_manage?: boolean;
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
  input_config?: {
    trigger_type?: string;
    // Pre-assigned documents the run loader merges into every run (Input tab).
    fixed_documents?: { uuid: string; title: string }[];
    // Workflow-level default model applied to every step without its own
    // override (set via the canvas "Model — all steps" selector).
    default_model?: string;
  };
  output_config?: { storage?: SaveOutputConfig; [key: string]: unknown };
  can_manage?: boolean;
  // Whether the current user may author validation artifacts (plan, test
  // inputs, expected outputs) and start validation runs. Implied by
  // can_manage; also true for an examiner reviewing this workflow's open
  // verification request. Absent on older payloads — fall back to can_manage.
  can_validate?: boolean;
  created_by?: AuthorRef | null;
}

export interface WorkflowErrorPayload {
  code: string;
  suggested_action?: 'convert_to_kb';
  oversize_documents?: Array<{ uuid: string; title: string; token_count: number }>;
  // 'single' — one document is too large on its own; 'combined' — the package
  // only overflows once concatenated into a single prompt.
  overflow_kind?: 'single' | 'combined';
  total_tokens?: number;
  input_budget?: number;
}

export interface WorkflowCitation {
  document_id?: string | null;
  document_title: string;
  page?: number | null;
  /** Last page of a chunk that crosses page breaks, when the cited passage
   *  could not be pinned to one page; rendered as "p. 2–3". */
  page_end?: number | null;
  /** Page was interpolated from OCR text, not measured. See #603. */
  page_approximate?: boolean;
  sheet?: string | null;
  chunk_id?: string | null;
  score?: number | null;
  similarity?: number | null;
  content_preview?: string;
  /** Set when several knowledge bases fed one step or task, so a chip can say
   *  which base a passage came from. */
  kb_uuid?: string | null;
  kb_title?: string | null;
  /** The exact source line the model was told to cite for this passage,
   *  e.g. "OMB Uniform Guidance — Subpart F · p. 12". Matches a bracketed
   *  citation in the output to this entry. */
  label?: string | null;
  /** The passage text itself (the chunk the claim rests on), for the
   *  citation popover. Older runs only carry `content_preview`. */
  content?: string | null;
  /** Statements in the output this passage was checked to support, each with
   *  the excerpt (verbatim from `content`) that supports it; the popover
   *  highlights the excerpts. Absent on runs from before citations were
   *  checked. */
  quotes?: { claim: string; quote: string }[] | null;
}

/** One knowledge base a grounded task reads, with the retrieval queries it is
 *  searched with (`{{ inputs.output }}` templating allowed). */
export interface KbGroundingTarget {
  kb_uuid: string;
  queries: string[];
}

/** A task's knowledge-base grounding (`data.kb_grounding`). A property of the
 *  task, independent of the step's data sources: each base has its own
 *  queries, so parallel tasks in one step can read different policy. The
 *  backend also reads an older flat form (`knowledge_bases: string[]` plus a
 *  shared `queries`). See backend kb_grounding.py. */
export interface KbGroundingConfig {
  knowledge_bases: KbGroundingTarget[];
  /** Passages per knowledge base per query. */
  k?: number;
  /** Total passages after merge and dedupe. */
  max_passages?: number;
  /** 0 = inherit each base's tuned relevance floor. */
  min_similarity?: number;
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
