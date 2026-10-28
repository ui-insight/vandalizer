import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'

type ToolCategory = 'read' | 'extract' | 'write' | 'workflow'

export const TOOL_META: Record<string, { label: string; category: ToolCategory }> = {
  analyze_documents: { label: 'Analyzing documents', category: 'read' },
  update_plan: { label: 'Updating the work plan', category: 'write' },
  search_documents:      { label: 'Searching documents',      category: 'read' },
  list_documents:        { label: 'Listing documents',        category: 'read' },
  list_folders:          { label: 'Listing folders',          category: 'read' },
  search_knowledge_base: { label: 'Searching knowledge base',  category: 'read' },
  list_knowledge_bases:  { label: 'Listing knowledge bases',  category: 'read' },
  list_extraction_sets:  { label: 'Listing extraction templates',  category: 'read' },
  list_skills:           { label: 'Finding Skills', category: 'read' },
  get_skill:             { label: 'Inspecting Skill', category: 'read' },
  select_skill:          { label: 'Updating active Skill', category: 'write' },
  list_workflows:        { label: 'Listing workflows',        category: 'read' },
  get_quality_info:      { label: 'Checking quality',         category: 'read' },
  search_library:        { label: 'Searching library',        category: 'read' },
  get_document_text:     { label: 'Reading document',         category: 'read' },
  get_app_help:          { label: 'Looking up help',          category: 'read' },
  fetch_url:             { label: 'Reading web page',         category: 'read' },
  web_search:            { label: 'Searching the web',        category: 'read' },
  run_extraction:        { label: 'Running extraction',       category: 'extract' },
  check_compliance:      { label: 'Checking compliance rules', category: 'workflow' },
  create_knowledge_base: { label: 'Creating knowledge base',  category: 'write' },
  add_documents_to_kb:   { label: 'Adding documents to KB',   category: 'write' },
  add_url_to_kb:         { label: 'Adding URL to KB',         category: 'write' },
  run_workflow:          { label: 'Running workflow',          category: 'workflow' },
  get_workflow_status:   { label: 'Checking workflow status',  category: 'workflow' },
  approve_workflow_step: { label: 'Approving workflow review', category: 'workflow' },
  reject_workflow_step:  { label: 'Rejecting workflow review', category: 'workflow' },
  list_test_cases:       { label: 'Listing test cases',         category: 'read' },
  propose_test_case:     { label: 'Preparing guided verification', category: 'extract' },
  run_validation:        { label: 'Running validation',         category: 'workflow' },
  create_extraction_from_document: { label: 'Building extraction from document', category: 'write' },
  list_optimization_recommendations: { label: 'Checking optimization suggestions', category: 'workflow' },
  get_optimization_run:  { label: 'Checking autovalidate run',  category: 'workflow' },
  start_optimization:    { label: 'Starting autovalidate',      category: 'write' },
  apply_optimization:    { label: 'Applying optimized config',  category: 'write' },
  regenerate_validation_plan: { label: 'Regenerating validation plan', category: 'write' },
  save_to_folder:        { label: 'Saving to folder',         category: 'write' },
  create_html_artifact:  { label: 'Creating page',        category: 'write' },
  revise_html_artifact:  { label: 'Updating page',        category: 'write' },
  get_html_artifact:     { label: 'Reading page',         category: 'read' },
  create_project:        { label: 'Creating project',         category: 'write' },
  list_project_documents:{ label: 'Listing project files',    category: 'read' },
  run_pin_on_project:    { label: 'Running pinned item',      category: 'workflow' },
  pin_to_project:        { label: 'Pinning to project',       category: 'write' },
  unpin_from_project:    { label: 'Removing project pin',     category: 'write' },
  set_project_status:    { label: 'Updating project status',  category: 'write' },
  propose_obligations: { label: 'Updating the RA inbox', category: 'write' },
  create_automation:     { label: 'Creating automation',      category: 'write' },
  create_workflow:       { label: 'Building workflow',         category: 'write' },
  get_workflow_definition: { label: 'Reading workflow steps',  category: 'read' },
  update_workflow:       { label: 'Updating workflow',         category: 'write' },
  get_certification_progress:      { label: 'Checking certification progress', category: 'read' },
  get_certification_module:        { label: 'Loading certification module',    category: 'read' },
  get_certification_lesson:        { label: 'Loading lesson',                  category: 'read' },
  provision_certification_lab:     { label: 'Setting up certification lab',    category: 'write' },
  check_certification_module:      { label: 'Grading certification module',    category: 'read' },
  complete_certification_module:   { label: 'Completing certification module', category: 'write' },
  submit_certification_assessment: { label: 'Saving self-assessment',          category: 'write' },
  save_certification_position:     { label: 'Saving lesson position',          category: 'write' },
}

export function getToolMeta(name: string) {
  return TOOL_META[name] || { label: name.replace(/_/g, ' '), category: 'read' as ToolCategory }
}


/** Only show short, user-facing targets. Never display generated HTML or tool instructions. */
export function toolTarget(call: ToolCallInfo, names: Record<string, string>): string {
  const args = call.args
  const parts: string[] = []
  for (const key of ['kb_uuid', 'knowledge_base_uuid', 'workflow_id', 'extraction_set_uuid', 'project_uuid', 'folder_uuid', 'document_uuid']) {
    const id = args[key]
    if (typeof id === 'string' && names[id]) parts.push(names[id])
  }
  const ids = args.document_uuids
  if (Array.isArray(ids) && ids.length) parts.push(ids.length === 1 && names[String(ids[0])] ? names[String(ids[0])] : `${ids.length} document${ids.length === 1 ? '' : 's'}`)
  for (const key of ['title', 'name', 'query', 'search', 'topic']) {
    const value = args[key]
    if (typeof value === 'string' && value.trim()) {
      parts.push(value.trim().slice(0, 140))
      break
    }
  }
  return [...new Set(parts)].join(' · ')
}

export function toolOutcome(result: ToolResultInfo): 'returned' | 'approval' | 'error' | 'canceled' {
  const value = Array.isArray(result.content) && result.content.length === 1 ? result.content[0] : result.content
  if (!value || typeof value !== 'object') return 'returned'
  const obj = value as Record<string, unknown>
  if (obj.status === 'canceled' || obj.status === 'cancelled') return 'canceled'
  if (obj.error || obj.status === 'failed' || obj.status === 'error') return 'error'
  if (obj.needs_confirmation) return 'approval'
  return 'returned'
}

export function activeToolLabel(call: ToolCallInfo): string {
  if (call.tool_name === 'create_html_artifact' || call.tool_name === 'revise_html_artifact') {
    return call.args.confirmed === true ? (call.tool_name === 'revise_html_artifact' ? 'Saving your page revision' : 'Saving your page') : 'Preparing your page preview'
  }
  return getToolMeta(call.tool_name).label
}
