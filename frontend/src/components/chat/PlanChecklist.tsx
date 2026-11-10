import { Check, Circle, Hourglass, Loader2 } from 'lucide-react'
import type { PlanTask } from '../../types/chat'

interface PlanChecklistProps {
  tasks: PlanTask[]
  isStreaming?: boolean
  /** Approval cards the reply left waiting; the plan can't read as done while any are. */
  waitingApprovals?: number
}

/** "1 of 4 done · 3 waiting for your approval": never "completed" while a
 * card is still waiting (support ticket: "✓ All 4 steps completed" with four
 * approval cards pending and nothing saved). */
export function planSummary(tasks: PlanTask[], waitingApprovals = 0): string {
  const completed = tasks.filter(t => t.status === 'completed').length
  const awaiting = tasks.filter(t => t.status === 'awaiting_approval').length
  const waiting = Math.max(awaiting, waitingApprovals)
  const parts = [`${completed} of ${tasks.length} done`]
  if (waiting) parts.push(`${waiting} waiting for your approval`)
  return parts.join(' · ')
}

/** "Done: project created, 3 deadlines added, 2 need your help, Page saved."
 * One finish line from each step's result, or its name when the step didn't
 * report one (support ticket: no clear finish to a multi-step setup). */
export function planFinishLine(tasks: readonly PlanTask[]): string {
  const outcomes = tasks.map(t => (t.result?.trim() || t.content).replace(/[.\s]+$/, ''))
  return `Done: ${outcomes.join(', ')}.`
}

/** Pinned live checklist for multi-step agent work (uplift plan Phase 8).
 * Driven by plan_update stream chunks from the update_plan tool. Collapses
 * to a single done-line once every task is completed and nothing waits. */
export function PlanChecklist({ tasks, isStreaming = true, waitingApprovals = 0 }: PlanChecklistProps) {
  if (!tasks.length) return null

  const completed = tasks.filter((t) => t.status === 'completed').length
  const awaiting = tasks.filter((t) => t.status === 'awaiting_approval').length
  const allDone = completed === tasks.length && !waitingApprovals && !awaiting

  if (allDone) {
    return (
      <div role="status" className="mt-2 flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800 border border-emerald-200">
        <Check size={14} className="shrink-0" />
        <span>
          {tasks.some(t => t.result?.trim())
            ? planFinishLine(tasks)
            : tasks.length === 1
              ? 'Task completed'
              : `All ${tasks.length} steps completed`}
        </span>
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-md bg-gray-50 px-3 py-2 border border-gray-200">
      <div role="status" className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
        Plan · {planSummary(tasks, waitingApprovals)}{!isStreaming && !awaiting && !waitingApprovals && ' · response ended'}
      </div>
      <ul className="space-y-2" aria-label="Plan steps">
        {tasks.map((task, i) => (
          <li key={i} className="flex flex-wrap items-start gap-2 text-xs" style={{ overflowWrap: 'anywhere' }}>
            {task.status === 'completed' ? (
              <Check size={13} className="mt-0.5 shrink-0 text-emerald-600" />
            ) : task.status === 'awaiting_approval' ? (
              <Hourglass size={13} className="mt-0.5 shrink-0 text-amber-600" />
            ) : task.status === 'in_progress' && isStreaming ? (
              <Loader2 size={13} className="mt-0.5 shrink-0 animate-spin text-blue-600" />
            ) : (
              <Circle size={13} className="mt-0.5 shrink-0 text-gray-300" />
            )}
            <span
              className={
                task.status === 'completed' || task.status === 'awaiting_approval'
                  ? 'min-w-0 flex-1 text-gray-600'
                  : task.status === 'in_progress'
                    ? 'min-w-0 flex-1 text-gray-900 font-medium'
                    : 'min-w-0 flex-1 text-gray-600'
              }
            >
              {task.status === 'in_progress' && isStreaming ? task.active_form : task.content}
              {task.status === 'completed' && task.result && <span className="text-gray-500"> · {task.result}</span>}
            </span>
            <span className="text-gray-600">{task.status === 'completed' ? 'Completed' : task.status === 'awaiting_approval' ? 'Waiting for your approval' : !isStreaming ? 'Not confirmed' : task.status === 'in_progress' ? 'Running' : 'Planned'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
