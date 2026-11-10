import type { WorkflowTask } from '../../types/workflow'

/** The task open in the task editor. A new task is a draft: it exists only
 * here until the user saves it.
 *
 * Support ticket: picking a type from "Add your first task" saved the task at
 * once, so closing its details with X left an empty task in the step whose
 * only option was Delete. Now the task is created on Save, and X on a draft
 * goes back to the task list with nothing added. */
export type TaskEdit = WorkflowTask & { draftStepId?: string }

export function newTaskDraft(stepId: string, name: string): TaskEdit {
  // New KB Query tasks default to answer mode (the intuitive behavior);
  // pre-existing ones without a mode keep returning raw passages.
  return { id: '', name, data: name === 'KnowledgeBaseQuery' ? { mode: 'answer' } : {}, draftStepId: stepId }
}

export function isTaskDraft(task: TaskEdit | null | undefined): boolean {
  return Boolean(task?.draftStepId)
}

/** Save the editor's task: create a draft in its step, or update an existing task. */
export function saveTaskEdit(
  task: TaskEdit,
  data: Record<string, unknown>,
  api: {
    addTask: (stepId: string, body: { name: string; data?: Record<string, unknown> }) => Promise<unknown>
    updateTask: (taskId: string, body: { data?: Record<string, unknown> }) => Promise<unknown>
  },
): Promise<unknown> {
  return task.draftStepId
    ? api.addTask(task.draftStepId, { name: task.name, data })
    : api.updateTask(task.id, { data })
}
