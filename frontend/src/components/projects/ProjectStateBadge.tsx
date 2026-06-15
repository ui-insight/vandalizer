import type { ProjectState } from '../../types/project'

const STATE_STYLES: Record<ProjectState, string> = {
  draft: 'bg-gray-100 text-gray-600',
  active: 'bg-green-100 text-green-700',
  submitted: 'bg-blue-100 text-blue-700',
  awarded: 'bg-purple-100 text-purple-700',
  closeout: 'bg-amber-100 text-amber-700',
  archived: 'bg-gray-200 text-gray-500',
}

export function ProjectStateBadge({ state }: { state: ProjectState }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATE_STYLES[state]}`}
    >
      {state}
    </span>
  )
}
