import { Check, Circle, Loader2 } from 'lucide-react'
import type { PlanTask } from '../../types/chat'

interface PlanChecklistProps {
  tasks: PlanTask[]
}

/** Pinned live checklist for multi-step agent work (uplift plan Phase 8).
 * Driven by plan_update stream chunks from the update_plan tool. Collapses
 * to a single done-line once every task is completed. */
export function PlanChecklist({ tasks }: PlanChecklistProps) {
  if (!tasks.length) return null

  const completed = tasks.filter((t) => t.status === 'completed').length
  const allDone = completed === tasks.length

  if (allDone) {
    return (
      <div className="mt-2 flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800 border border-emerald-200">
        <Check size={14} className="shrink-0" />
        <span>
          {tasks.length === 1
            ? 'Task completed'
            : `All ${tasks.length} steps completed`}
        </span>
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-md bg-gray-50 px-3 py-2 border border-gray-200">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        Plan · {completed}/{tasks.length} done
      </div>
      <ul className="space-y-1">
        {tasks.map((task, i) => (
          <li key={i} className="flex items-start gap-2 text-xs">
            {task.status === 'completed' ? (
              <Check size={13} className="mt-0.5 shrink-0 text-emerald-600" />
            ) : task.status === 'in_progress' ? (
              <Loader2 size={13} className="mt-0.5 shrink-0 animate-spin text-blue-600" />
            ) : (
              <Circle size={13} className="mt-0.5 shrink-0 text-gray-300" />
            )}
            <span
              className={
                task.status === 'completed'
                  ? 'text-gray-400 line-through'
                  : task.status === 'in_progress'
                    ? 'text-gray-900 font-medium'
                    : 'text-gray-600'
              }
            >
              {task.status === 'in_progress' ? task.active_form : task.content}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
