import { useProject } from '../../hooks/useProjects'

export function ProjectContextRunOption({ projectUuid, checked, onChange, disabled }: {
  projectUuid: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean
}) {
  const { project } = useProject(projectUuid)
  if (!project?.context && !checked) return null
  return <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
    <label className="flex items-center gap-2 text-sm font-medium text-slate-700"><input type="checkbox" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)} className="h-4 w-4 accent-highlight" />Use project context for this run</label>
    <p className="mt-1 pl-6 text-xs leading-relaxed text-slate-500">Applies your saved brief to Prompt and Formatter steps. A copy is kept with this run; step instructions take precedence.</p>
  </div>
}
