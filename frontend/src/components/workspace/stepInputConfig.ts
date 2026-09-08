import type { WorkflowStep, WorkflowTask } from '../../types/workflow'

export type TaskInputSource = 'step_input' | 'select_document' | 'workflow_documents'

/**
 * Where a step's data comes from. This is a property of the *step*: every task
 * in a step is handed an identical copy of the step's payload and the tasks run
 * in parallel, so there is one answer per step, not one per task.
 */
export interface StepInputValue {
  sources: TaskInputSource[]
  selectedDocUuid: string
}

/** Keys that carry input configuration, on a step's or a task's `data`. */
export const STEP_INPUT_KEYS = ['input_sources', 'input_source', 'selected_document_uuid'] as const

/** A task with this flag keeps its own input instead of the step's. */
export const TASK_INPUT_OVERRIDE_KEY = 'override_step_input'

const VALID_SOURCES: TaskInputSource[] = ['step_input', 'select_document', 'workflow_documents']

export const DEFAULT_STEP_INPUT: StepInputValue = { sources: ['step_input'], selectedDocUuid: '' }

/** Human-readable name for each source — mirrors INPUT_SOURCE_LABELS in the engine. */
export const INPUT_SOURCE_LABELS: Record<TaskInputSource, string> = {
  step_input: 'Step Input',
  select_document: 'Selected Document',
  workflow_documents: 'Workflow Documents',
}

/** Read the input config out of a step's or task's `data` bag. */
export function readInputValue(data: Record<string, unknown> | undefined): StepInputValue {
  const raw = data?.input_sources
  let sources: TaskInputSource[] = []
  if (Array.isArray(raw)) {
    sources = raw.filter((s): s is TaskInputSource => VALID_SOURCES.includes(s as TaskInputSource))
  }
  if (sources.length === 0) {
    const legacy = data?.input_source as TaskInputSource | undefined
    sources = legacy && VALID_SOURCES.includes(legacy) ? [legacy] : ['step_input']
  }
  // De-dupe while keeping author order.
  sources = sources.filter((s, i) => sources.indexOf(s) === i)
  return {
    sources,
    selectedDocUuid: typeof data?.selected_document_uuid === 'string' ? data.selected_document_uuid : '',
  }
}

/** Whether input has actually been configured at this level (vs. defaulted). */
export function definesInput(data: Record<string, unknown> | undefined): boolean {
  if (!data) return false
  return STEP_INPUT_KEYS.some(k => k in data)
}

/** Whether a task opts out of its step's input with the advanced override. */
export function taskOverridesStepInput(task: Pick<WorkflowTask, 'data'>): boolean {
  return Boolean(task.data?.[TASK_INPUT_OVERRIDE_KEY])
}

/** The `data` patch that writes an input config onto a step or a task. */
export function inputValuePatch(value: StepInputValue): Record<string, unknown> {
  const sources = value.sources.length > 0 ? value.sources : DEFAULT_STEP_INPUT.sources
  return {
    input_sources: sources,
    // Kept for the legacy single-value readers that still exist server-side.
    input_source: sources[0],
    selected_document_uuid: sources.includes('select_document') ? value.selectedDocUuid : '',
  }
}

/** Toggle one source on or off, never leaving the selection empty. */
export function toggleSource(sources: TaskInputSource[], src: TaskInputSource): TaskInputSource[] {
  if (sources.includes(src)) {
    const next = sources.filter(s => s !== src)
    return next.length > 0 ? next : [src]
  }
  return [...sources, src]
}

export function sameInputValue(a: StepInputValue, b: StepInputValue): boolean {
  if (a.sources.length !== b.sources.length) return false
  if (a.sources.some((s, i) => s !== b.sources[i])) return false
  const aDoc = a.sources.includes('select_document') ? a.selectedDocUuid : ''
  const bDoc = b.sources.includes('select_document') ? b.selectedDocUuid : ''
  return aDoc === bDoc
}

/**
 * What a step's Input tab should show, and what lifting it costs.
 *
 * Input used to be configured per task. For a step authored that way the step
 * itself has nothing stored, so the tab seeds from the tasks: if they all agree
 * (the overwhelmingly common case) that shared answer is simply the step's.
 * When they disagree there is no single right answer, so the first task's wins
 * and the rest are reported — the caller pins those onto the advanced per-task
 * override when the author saves, rather than silently repointing them.
 */
export function deriveStepInput(step: Pick<WorkflowStep, 'data' | 'tasks'>): {
  value: StepInputValue
  /** True when the value came from the step itself, not inferred from tasks. */
  fromStep: boolean
  /** Tasks whose own config differs from `value` — only ever non-empty when inferred. */
  divergentTasks: WorkflowTask[]
} {
  if (definesInput(step.data)) {
    return { value: readInputValue(step.data), fromStep: true, divergentTasks: [] }
  }
  const configured = (step.tasks || []).filter(t => definesInput(t.data))
  if (configured.length === 0) {
    return { value: { ...DEFAULT_STEP_INPUT }, fromStep: false, divergentTasks: [] }
  }
  const value = readInputValue(configured[0].data)
  const divergentTasks = configured
    .slice(1)
    .filter(t => !sameInputValue(readInputValue(t.data), value))
  return { value, fromStep: false, divergentTasks }
}

/**
 * The input a task actually runs with: its own when it overrides, the step's
 * otherwise. Mirrors `apply_step_input_config` in the backend engine, and is
 * what the editor sends when testing a single task in isolation.
 */
export function effectiveTaskInput(
  step: Pick<WorkflowStep, 'data' | 'tasks'>,
  task: Pick<WorkflowTask, 'data'>,
): StepInputValue {
  if (taskOverridesStepInput(task)) return readInputValue(task.data)
  if (definesInput(step.data)) return readInputValue(step.data)
  return readInputValue(task.data)
}
