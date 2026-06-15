import { useCallback, useEffect, useState, type ComponentType } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Workflow, FileSearch, Zap, BookOpen, X } from 'lucide-react'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useSearchSets } from '../../hooks/useExtractions'
import { listProjectPins, addProjectPin, removeProjectPin } from '../../api/projects'
import type { ProjectPin } from '../../types/project'

const TYPE_META: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; label: string }> = {
  workflow: { icon: Workflow, label: 'Workflow' },
  extraction: { icon: FileSearch, label: 'Extraction' },
  automation: { icon: Zap, label: 'Automation' },
  knowledge_base: { icon: BookOpen, label: 'Knowledge base' },
}

const key = (p: { pin_type: string; target_id: string }) => `${p.pin_type}:${p.target_id}`

/**
 * Pinned tools for a project — references (not copies) to workflows/extractions
 * you use for this grant, for quick access. Clicking one opens it inside the
 * scoped project so it runs against the project's documents.
 */
export function ProjectPinsSection({ projectUuid, onChange }: { projectUuid: string; onChange?: () => void }) {
  const navigate = useNavigate()
  const { workflows } = useWorkflows()
  const { searchSets } = useSearchSets()
  const [pins, setPins] = useState<ProjectPin[]>([])
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => {
    listProjectPins(projectUuid).then(setPins).catch(() => {})
  }, [projectUuid])
  useEffect(() => { load() }, [load])

  const pinnedSet = new Set(pins.map(key))

  const pin = async (pinType: string, targetId: string) => {
    try {
      await addProjectPin(projectUuid, { pin_type: pinType, target_id: targetId })
      load()
      onChange?.()
    } catch { /* ignore */ }
  }

  const unpin = async (p: ProjectPin) => {
    try {
      await removeProjectPin(projectUuid, p.pin_type, p.target_id)
      load()
      onChange?.()
    } catch { /* ignore */ }
  }

  const open = (p: ProjectPin) => {
    const base = {
      mode: 'files' as 'files' | 'automations',
      tab: undefined, workflow: undefined as string | undefined,
      extraction: undefined as string | undefined, automation: undefined as string | undefined,
      kb: undefined, project: projectUuid, workflow_share_token: undefined,
    }
    if (p.pin_type === 'workflow') navigate({ to: '/', search: { ...base, workflow: p.target_id } })
    else if (p.pin_type === 'extraction') navigate({ to: '/', search: { ...base, extraction: p.target_id } })
    else if (p.pin_type === 'automation') navigate({ to: '/', search: { ...base, mode: 'automations', automation: p.target_id } })
  }

  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Pinned tools</h2>
        <button onClick={() => setAdding(a => !a)} className="flex items-center gap-1 text-sm text-highlight hover:underline">
          <Plus size={14} /> Pin a tool
        </button>
      </div>

      {adding && (
        <div className="mb-3 rounded-lg border border-gray-200 bg-white p-3">
          <PickerList title="Workflows" items={workflows.map(w => ({ id: w.id, name: w.name }))} pinType="workflow" pinnedSet={pinnedSet} onPin={pin} />
          <PickerList title="Extractions" items={searchSets.map(s => ({ id: s.uuid, name: s.title }))} pinType="extraction" pinnedSet={pinnedSet} onPin={pin} />
        </div>
      )}

      {pins.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 p-4 text-center text-sm text-gray-400">
          No pinned tools. Pin the workflows and extractions you use for this project.
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {pins.map(p => {
            const meta = TYPE_META[p.pin_type] ?? TYPE_META.workflow
            const Icon = meta.icon
            return (
              <div key={key(p)} className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-3">
                <Icon size={16} className="shrink-0 text-gray-400" />
                <button onClick={() => open(p)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-sm font-medium text-gray-900">{p.name}</div>
                  <div className="text-xs text-gray-400">{meta.label}</div>
                </button>
                <button onClick={() => unpin(p)} title="Unpin" className="p-1 text-gray-300 hover:text-red-500">
                  <X size={14} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PickerList({ title, items, pinType, pinnedSet, onPin }: {
  title: string
  items: { id: string; name: string }[]
  pinType: string
  pinnedSet: Set<string>
  onPin: (pinType: string, targetId: string) => void
}) {
  if (items.length === 0) return null
  const available = items.filter(i => !pinnedSet.has(`${pinType}:${i.id}`))
  return (
    <div className="mb-2 last:mb-0">
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">{title}</div>
      {available.length === 0 ? (
        <div className="text-xs text-gray-400">All pinned.</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {available.slice(0, 30).map(i => (
            <button
              key={i.id}
              onClick={() => onPin(pinType, i.id)}
              className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:border-highlight"
            >
              + {i.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
