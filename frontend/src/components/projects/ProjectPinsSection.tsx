import { useCallback, useEffect, useState, type ComponentType } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, Workflow, FileSearch, Zap, BookOpen, X, Search } from 'lucide-react'
import { useWorkflows } from '../../hooks/useWorkflows'
import { useSearchSets } from '../../hooks/useExtractions'
import { useAutomations } from '../../hooks/useAutomations'
import { useKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { listProjectPins, addProjectPin, removeProjectPin } from '../../api/projects'
import type { ProjectPin } from '../../types/project'

const TYPE_META: Record<string, { icon: ComponentType<{ size?: number; className?: string }>; label: string }> = {
  workflow: { icon: Workflow, label: 'Workflow' },
  extraction: { icon: FileSearch, label: 'Extraction' },
  automation: { icon: Zap, label: 'Automation' },
  knowledge_base: { icon: BookOpen, label: 'Knowledge base' },
}

const key = (p: { pin_type: string; target_id: string }) => `${p.pin_type}:${p.target_id}`

/** Chips rendered per list before the picker asks you to narrow it. */
const PICKER_CAP = 30

/**
 * Pinned tools for a project — references (not copies) to workflows/extractions
 * you use for this grant, for quick access. Clicking one opens it inside the
 * scoped project so it runs against the project's documents.
 */
export function ProjectPinsSection({ projectUuid, onChange, onOpen }: { projectUuid: string; onChange?: () => void; onOpen?: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])
  // Workflows are searched server-side: the list endpoint caps a page at 500,
  // so a client-side filter over one page would hide anything past the cap —
  // the same failure this picker used to have silently. The other three hooks
  // return their whole set today and are narrowed here.
  const { workflows, total: workflowTotal } = useWorkflows({ search: debouncedQuery || undefined })
  const q = debouncedQuery.toLowerCase()
  const matches = (name: string) => !q || name.toLowerCase().includes(q)
  const { searchSets } = useSearchSets()
  const { automations } = useAutomations()
  const { knowledgeBases } = useKnowledgeBases()
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
      mode: undefined as 'files' | 'automations' | undefined,
      tab: undefined, workflow: undefined as string | undefined,
      extraction: undefined as string | undefined, automation: undefined as string | undefined,
      kb: undefined as string | undefined, project: projectUuid, workflow_share_token: undefined,
    }
    if (p.pin_type === 'workflow') navigate({ to: '/', search: { ...base, mode: 'files', workflow: p.target_id } })
    else if (p.pin_type === 'extraction') navigate({ to: '/', search: { ...base, mode: 'files', extraction: p.target_id } })
    else if (p.pin_type === 'automation') navigate({ to: '/', search: { ...base, mode: 'automations', automation: p.target_id } })
    else if (p.pin_type === 'knowledge_base') navigate({ to: '/', search: { ...base, kb: p.target_id } })
    // Close the Manage modal so the tool we just navigated to is actually
    // visible — otherwise the overlay stays up and the click looks like a no-op.
    onOpen?.()
  }

  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Pinned tools</h2>
        <button type="button" onClick={() => setAdding(a => !a)} className="flex items-center gap-1 text-sm text-highlight hover:underline">
          <Plus size={14} /> Pin a tool
        </button>
      </div>

      {adding && (
        <div className="mb-3 rounded-lg border border-gray-200 bg-white p-3">
          <label className="mb-3 flex items-center gap-2 rounded-md border border-gray-200 px-2 py-1.5 text-sm focus-within:border-highlight">
            <Search size={14} className="shrink-0 text-gray-400" />
            <input
              type="search"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search tools by name"
              aria-label="Search tools to pin"
              className="w-full bg-transparent text-gray-900 outline-none placeholder:text-gray-400"
            />
          </label>
          <PickerList title="Workflows" items={workflows.map(w => ({ id: w.id, name: w.name }))} total={workflowTotal} query={debouncedQuery} pinType="workflow" pinnedSet={pinnedSet} onPin={pin} />
          <PickerList title="Extractions" items={searchSets.filter(s => matches(s.title)).map(s => ({ id: s.uuid, name: s.title }))} query={debouncedQuery} pinType="extraction" pinnedSet={pinnedSet} onPin={pin} />
          <PickerList title="Automations" items={automations.filter(a => matches(a.name)).map(a => ({ id: a.id, name: a.name }))} query={debouncedQuery} pinType="automation" pinnedSet={pinnedSet} onPin={pin} />
          <PickerList title="Knowledge bases" items={knowledgeBases.filter(k => matches(k.title)).map(k => ({ id: k.uuid, name: k.title }))} query={debouncedQuery} pinType="knowledge_base" pinnedSet={pinnedSet} onPin={pin} />
          {debouncedQuery && workflows.length + searchSets.filter(s => matches(s.title)).length + automations.filter(a => matches(a.name)).length + knowledgeBases.filter(k => matches(k.title)).length === 0 && (
            <div className="text-xs text-gray-500">Nothing matches “{debouncedQuery}”.</div>
          )}
        </div>
      )}

      {pins.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 p-4 text-center text-sm text-gray-500">
          No pinned tools. Pin the workflows, extractions, automations, and knowledge bases you use for this project.
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {pins.map(p => {
            const meta = TYPE_META[p.pin_type] ?? TYPE_META.workflow
            const Icon = meta.icon
            return (
              <div key={key(p)} className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-3">
                <Icon size={16} className="shrink-0 text-gray-500" />
                <button type="button" onClick={() => open(p)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-sm font-medium text-gray-900">{p.name}</div>
                  <div className="text-xs text-gray-500">{meta.label}</div>
                </button>
                <button type="button" onClick={() => unpin(p)} title="Unpin" aria-label="Unpin" className="p-1 text-gray-500 hover:text-red-500">
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

function PickerList({ title, items, total, query, pinType, pinnedSet, onPin }: {
  title: string
  items: { id: string; name: string }[]
  /** Server-side match count when `items` is one page of a larger set. */
  total?: number
  query?: string
  pinType: string
  pinnedSet: Set<string>
  onPin: (pinType: string, targetId: string) => void
}) {
  if (items.length === 0) return null
  const available = items.filter(i => !pinnedSet.has(`${pinType}:${i.id}`))
  const shown = available.slice(0, PICKER_CAP)
  // Two ways this list can be shorter than the truth: the page the server
  // sent is not the whole set (`total`), or the chip cap trimmed it. Either
  // way say so — a silent cut reads as "that workflow was deleted".
  const known = Math.max(total ?? items.length, items.length)
  const truncated = shown.length < available.length || items.length < known
  return (
    <div className="mb-2 last:mb-0">
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">{title}</div>
      {available.length === 0 ? (
        <div className="text-xs text-gray-500">All pinned.</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {shown.map(i => (
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
      {truncated && (
        <div className="mt-1 text-xs text-gray-500">
          Showing {shown.length} of {known}{query ? ' matching' : ''}. Search to narrow the list.
        </div>
      )}
    </div>
  )
}
