import { FileText, PlayCircle, Send, Award, Archive, ClipboardCheck } from 'lucide-react'
import type { ProjectState } from '../../types/project'

const states = {
  draft: { tone: 'neutral', icon: FileText },
  active: { tone: 'info', icon: PlayCircle },
  submitted: { tone: 'info', icon: Send },
  awarded: { tone: 'success', icon: Award },
  closeout: { tone: 'neutral', icon: ClipboardCheck },
  archived: { tone: 'neutral', icon: Archive },
} as const

export function ProjectStateBadge({ state }: { state: ProjectState }) {
  const { tone, icon: Icon } = states[state] ?? states.draft
  return <span className="workspace-status-badge" data-tone={tone}><Icon size={14} aria-hidden="true" />{state.charAt(0).toUpperCase() + state.slice(1)}</span>
}
