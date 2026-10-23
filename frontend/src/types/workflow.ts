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
  /** A web result's address (Web Search step); the chip opens it. */
  url?: string | null;
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
  /** For a passage holding only items of a list, the sentence earlier in its
   *  section that says what the list is ("… must request prior written
   *  approval … for the following …:"); shown above the passage. */
  lead_in?: string | null;
}

/** One cited claim of a chat answer, checked against the passage it cites
 *  (backend chat_claim_check). The UI finds its chip by `citations` and the
 *  claim text before it. */
export interface ClaimCheck {
  claim: string;
  /** The bracketed citations the claim carries, as written. */
  citations: string[];
  /** Indexes into the message's citations. */
  cites: number[];
  status: 'verified' | 'unverified' | 'unchecked';
  reason?: string;
  /** The checker's few words on why the passage does not state it. */
  why?: string;
  /** The excerpt that states a verified claim (verbatim from the passage). */
  quote?: string;
  source?: number;
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
  /** The run's model, and the models its steps actually ran on. */
  model?: string | null;
  models_used?: string[];
  /** Where each statement in the outputs came from, traced after the run
   *  completed (backend output_sourcing.py). Absent on older runs. */
  sourcing?: WorkflowSourcing | null;
}

/** The place one statement was traced to: an input document, or a
 *  knowledge-base passage the run retrieved. `excerpt` is the source's text
 *  around the statement, with the supporting `quote` at
 *  `excerpt.slice(quote_start, quote_end)`. The page is the engine's, from
 *  the document's page markers; `page_approximate` marks a scan. */
export interface SourcingLink {
  kind: 'document' | 'kb';
  quote: string;
  excerpt: string;
  quote_start: number;
  quote_end: number;
  page?: number | null;
  page_end?: number | null;
  page_approximate?: boolean;
  document_uuid?: string | null;
  document_title?: string | null;
  kb_title?: string | null;
  kb_uuid?: string | null;
  label?: string | null;
  chunk_id?: string | null;
}

/** One statement of an output. `s`/`e` are code-point offsets into a text
 *  output, or into the string leaf at path `p` of a structured one (absent
 *  for a whole number or boolean leaf). A text output that is JSON also
 *  gives `p` and the offsets inside that leaf, `ls`/`le`. `src` indexes
 *  `WorkflowSourcing.sources`; `t` marks a statement no source can show — a
 *  claim that something is absent, or a judgment. */
export interface SourcedStatement {
  s?: number;
  e?: number;
  p?: Array<string | number>;
  ls?: number;
  le?: number;
  src?: number;
  t?: 'absent' | 'verdict';
  /** Still being checked: only while `WorkflowSourcing.status` is `running`. */
  w?: 1;
}

export interface SourcingTarget {
  format: 'text' | 'json' | 'none';
  statements: SourcedStatement[];
  summary: { statements: number; traced: number };
}

/** Targets: `final` (the deliverable), `step:<steps_output key>`, or `test`.
 *  While `running`, `targets` holds what is settled so far — the
 *  deliverable first — and grows; a source's index never changes. */
export interface WorkflowSourcing {
  status: 'pending' | 'running' | 'done' | 'failed';
  version?: number;
  sources?: SourcingLink[];
  targets?: Record<string, SourcingTarget>;
  error?: string;
  unchecked?: number;
  errors?: number;
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
