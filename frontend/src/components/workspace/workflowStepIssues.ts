import type { WorkflowStep } from '../../types/workflow'

/**
 * Configuration problems that make a step unable to do anything useful, found
 * from the persisted workflow rather than a run. The editor uses these to
 * block Run/Update/Test Step and to badge the step on the canvas; the engine
 * applies the same rule at execution time as the backstop for workflows
 * created through the API.
 */

/** A Prompt task with nothing to ask: no inline text and no saved prompt linked. */
export function promptTaskIsEmpty(taskName: string, data: Record<string, unknown> | undefined): boolean {
  if (taskName !== 'Prompt') return false
  const d = data ?? {}
  // A linked Library prompt is resolved at run time, so its body isn't in the
  // task data — the link alone counts as configured. (A linked prompt whose
  // body is still empty is caught by the engine.)
  if (typeof d.saved_prompt_uuid === 'string' && d.saved_prompt_uuid) return false
  const prompt = d.prompt
  return !(typeof prompt === 'string' && prompt.trim())
}

export interface UnfinishedStep {
  stepId: string
  /** 1-based, numbered the way the canvas shows it (hidden Document trigger steps excluded). */
  stepNumber: number
  stepName: string
  taskId: string
  /** The label shown on the task row — the user's name for it, else the type. */
  taskLabel: string
  reason: string
}

export function findUnfinishedSteps(steps: WorkflowStep[]): UnfinishedStep[] {
  const out: UnfinishedStep[] = []
  let stepNumber = 0
  for (const step of steps) {
    if (step.name === 'Document' && step.tasks.length === 0) continue
    stepNumber += 1
    for (const task of step.tasks) {
      if (promptTaskIsEmpty(task.name, task.data)) {
        const name = task.data?.name
        out.push({
          stepId: step.id,
          stepNumber,
          stepName: step.name,
          taskId: task.id,
          taskLabel: typeof name === 'string' && name ? name : task.name,
          reason: 'has no prompt',
        })
      }
    }
  }
  return out
}

/** One line for the Run button area: "Step 2 "Summarize" has no prompt — …". */
export function describeUnfinishedSteps(issues: UnfinishedStep[]): string | null {
  if (issues.length === 0) return null
  const first = issues[0]
  const lead = `Step ${first.stepNumber} "${first.taskLabel}" ${first.reason}`
  const rest = issues.length > 1 ? ` (and ${issues.length - 1} more)` : ''
  return `${lead}${rest} — open the step and add instructions before running`
}
