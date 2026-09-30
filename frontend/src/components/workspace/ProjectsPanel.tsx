import { usePanelVisible } from '../shared/PanelVisibility'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, FolderKanban, HelpCircle, MoreHorizontal, Copy } from 'lucide-react'
import { useProjects } from '../../hooks/useProjects'
import { useToast } from '../../contexts/ToastContext'
import type { Project } from '../../types/project'
import { ProjectStateBadge } from '../projects/ProjectStateBadge'
import { ProjectSummaryStats } from '../projects/ProjectSummaryStats'
import { ProjectsExplainer } from '../projects/ProjectsExplainer'

/**
 * The Projects drawer — a slideout panel (like Automations/Knowledge) listing
 * the user's projects and the only project list in the app. Clicking one scopes
 * the whole workspace (files, chat, …) to that project; managing/sharing/leaving
 * happens in the in-workspace Manage panel opened from the project context bar.
 */
export function ProjectsPanel() {
  const navigate = useNavigate()
  const visible = usePanelVisible()
  const visibleRef = useRef(visible)
  visibleRef.current = visible
  const { projects, loading, error, refresh, create, duplicate } = useProjects()
  const { toast } = useToast()
  const [newName, setNewName] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const createPending = useRef(false)
  const duplicatePending = useRef(false)
  const [visibleLimit, setVisibleLimit] = useState(40)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('updated')
  const visibleProjects = useMemo(() => projects.filter(p => `${p.title} ${p.description ?? ''}`.toLowerCase().includes(search.trim().toLowerCase())).sort((a, b) => sort === 'name' ? a.title.localeCompare(b.title) : new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()), [projects, search, sort])
  const [creating, setCreating] = useState(false)
  const [showExplainer, setShowExplainer] = useState(false)
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null)

  // Scope the workspace to the project. The `?project=` param is consumed by
  // WorkspaceContext, which activates the project scope and lands in chat.
  // Switch the stored mode to chat *first* so the drawer doesn't linger via the
  // localStorage fallback while the (async) project scope resolves.
  const openProject = (uuid: string) => {
    try { localStorage.setItem('workspace:mode', 'chat') } catch { /* URL navigation remains available. */ }
    navigate({
      to: '/',
      search: {
        mode: 'chat',
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
        project: uuid,
        workflow_share_token: undefined,
      },
    })
  }

  const handleCreate = async () => {
    if (!newName.trim() || createPending.current) return
    createPending.current = true
    setCreateError(null)
    setCreating(true)
    try {
      const project = await create(newName.trim())
      if (mounted.current) {
        setNewName('')
        if (visibleRef.current) openProject(project.uuid)
        else toast(`Created “${project.title}”`, 'success', { label: 'Open project', onClick: () => openProject(project.uuid) })
      }
    } catch (error) {
      setCreateError(`${error instanceof Error ? error.message : 'Could not create project'}. Your name is preserved; retry Create.`)
    } finally {
      createPending.current = false
      setCreating(false)
    }
  }

  const handleDuplicate = async (p: Project) => {
    if (duplicatePending.current) return
    duplicatePending.current = true
    setMenuOpenId(null)
    setDuplicatingId(p.uuid)
    try {
      await duplicate(p.uuid)
      toast(`Duplicating “${p.title}” — copying files in the background`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to duplicate project', 'error')
    } finally {
      duplicatePending.current = false
      setDuplicatingId(null)
    }
  }

  return (
    <div role="region" aria-label="Projects list" className="relative h-full overflow-auto bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-5 py-4">
        <FolderKanban className="h-5 w-5 text-gray-400" />
        <h2 className="text-base font-semibold text-gray-900">Projects</h2>
        <button
          onClick={() => setShowExplainer(true)}
          className="inline-flex items-center gap-1 rounded-full border border-gray-300 px-2.5 py-1 text-[11px] font-semibold text-gray-500 hover:bg-gray-50 hover:text-gray-700"
        >
          <HelpCircle size={12} />
          What are Projects?
        </button>
        <span className="ml-auto text-xs text-gray-600">{loading ? 'Loading…' : error ? 'Unavailable' : `${projects.length} projects`}</span>
      </div>

      {showExplainer && <ProjectsExplainer onClose={() => setShowExplainer(false)} />}

      <div className="p-5 pb-24">
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            disabled={creating}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.nativeEvent.isComposing && handleCreate()}
            placeholder="New project name..."
            aria-label="New project name"
            className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          />
          <button
            onClick={handleCreate}
            aria-label="Create project"
            disabled={creating || !newName.trim()}
            className="flex items-center gap-1 rounded-lg bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
          >
            <Plus size={16} /> <span>{creating ? 'Creating…' : 'Create'}</span>
          </button>
        </div>

        {createError && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{createError}</p>}
        {projects.length > 0 && <div className="project-list-tools">
          <input type="search" aria-label="Search projects" placeholder="Search projects…" value={search} onChange={e => { setSearch(e.target.value); setVisibleLimit(40) }} />
          <select aria-label="Sort projects" value={sort} onChange={e => { setSort(e.target.value); setVisibleLimit(40) }}><option value="updated">Recently updated</option><option value="name">Name A–Z</option></select>
        </div>}
        <div className="mt-4 space-y-2">
          {loading ? (
            <div role="status" className="text-sm text-gray-600">Loading projects…</div>
          ) : error ? (<div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Projects could not be loaded. <button onClick={() => refresh()} className="ml-2 rounded border border-red-300 px-2 py-1 underline">Retry projects</button></div>) : projects.length === 0 ? (
            <div className="project-empty"><h3>Bring your work together</h3><p>A project keeps related files, knowledge and reusable tools in one place. Name your first project above to get started.</p></div>
          ) : (
            visibleProjects.length === 0 ? <p role="status" className="py-6 text-sm text-gray-600">No projects match “{search}”. <button type="button" onClick={() => setSearch('')}>Clear search</button></p> : visibleProjects.slice(0, visibleLimit).map(p => (
              <div
                key={p.uuid}
                className="group relative rounded-lg border border-gray-200 bg-white transition-colors hover:border-highlight"
              >
                <button
                  onClick={() => openProject(p.uuid)}
                  className="flex w-full flex-col items-start p-3 text-left"
                >
                  <div className="flex w-full flex-col items-start gap-2 pr-7">
                    <span className="w-full min-w-0 break-words font-medium text-gray-900">{p.title}</span>
                    <ProjectStateBadge state={p.state} />
                  </div>
                  {p.description && (
                    <span className="mt-1 break-words text-sm text-gray-600">{p.description}</span>
                  )}
                  <ProjectSummaryStats capabilities={p.capabilities} className="mt-2" />
                  <span className="mt-2 text-xs text-gray-600">{p.role ? `${p.role === 'viewer' ? 'Read-only' : p.role === 'owner' ? 'Owner' : 'Editor'} · ` : ''}Updated {Number.isNaN(new Date(p.updated_at).getTime()) ? 'date unavailable' : new Date(p.updated_at).toLocaleDateString()}</span>
                  {duplicatingId === p.uuid && <span role="status" className="mt-2 text-sm text-gray-600">Requesting a copy…</span>}
                </button>

                {/* Per-project actions. Kept outside the card <button> above —
                    a button can't be nested inside another button. */}
                <div className="absolute right-1.5 top-1.5">
                  <button
                    onClick={() => setMenuOpenId(menuOpenId === p.uuid ? null : p.uuid)}
                    disabled={!!duplicatingId}
                    aria-label={`Actions for project: ${p.title}`}
                    className="flex h-7 w-7 items-center justify-center rounded-md text-gray-500 transition-opacity hover:bg-gray-100 hover:text-gray-600 focus:opacity-100 group-hover:opacity-100 disabled:opacity-50 disabled:cursor-wait aria-expanded:opacity-100"
                    aria-expanded={menuOpenId === p.uuid}
                  >
                    <MoreHorizontal size={16} />
                  </button>

                  {menuOpenId === p.uuid && (
                    <>
                      {/* Click-away backdrop */}
                      <div
                        className="fixed inset-0 z-40"
                        onClick={() => setMenuOpenId(null)}
                      />
                      <div className="absolute right-0 top-8 z-50 w-40 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                        <button
                          onClick={() => handleDuplicate(p)}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                        >
                          <Copy size={14} />
                          Duplicate
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
        {!loading && !error && visibleProjects.length > visibleLimit && <button onClick={() => setVisibleLimit(limit => limit + 40)} className="mt-4 rounded-lg border border-gray-300 px-4 py-2 text-sm">Show more projects ({visibleProjects.length - visibleLimit} remaining)</button>}
      </div>
    </div>
  )
}
