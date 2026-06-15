import {
  FileText,
  Sparkles,
  Workflow,
  FileSearch,
  Zap,
  Users,
  type LucideIcon,
} from 'lucide-react'
import type { ProjectCapabilities } from '../../types/project'

/**
 * A compact, at-a-glance row of "what's inside this project" — files, indexed
 * docs, pinned tools, members. Rendered on explorer cards so you can see what a
 * project holds without opening it. Mirrors the capability grid on the project
 * home, just condensed.
 *
 * Zero-count stats are hidden to keep cards tidy; Files always shows so an
 * empty project still reads as "0 files" rather than blank.
 */
export function ProjectSummaryStats({
  capabilities,
  className = '',
}: {
  capabilities: ProjectCapabilities | undefined
  className?: string
}) {
  if (!capabilities) return null
  const c = capabilities

  const stats: { icon: LucideIcon; value: number; label: string; always?: boolean }[] = [
    { icon: FileText, value: c.files.count, label: 'files', always: true },
    { icon: Sparkles, value: c.knowledge.documents, label: 'indexed' },
    { icon: Workflow, value: c.workflows.count, label: 'workflows' },
    { icon: FileSearch, value: c.extractions.count, label: 'extractions' },
    { icon: Zap, value: c.automations.count, label: 'automations' },
    { icon: Users, value: c.members.count, label: 'members' },
  ]

  const shown = stats.filter(s => s.always || s.value > 0)

  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 ${className}`}>
      {shown.map(({ icon: Icon, value, label }) => (
        <span key={label} className="inline-flex items-center gap-1" title={`${value} ${label}`}>
          <Icon size={12} className="text-gray-400" />
          {value}
        </span>
      ))}
    </div>
  )
}
