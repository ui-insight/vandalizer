import { useState } from 'react'
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
  const { projects, loading, create, duplicate } = useProjects()
  const { toast } = useToast()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [showExplainer, setShowExplainer] = useState(false)
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null)

  // Scope the workspace to the project. The `?project=` param is consumed by
  // WorkspaceContext, which activates the project scope and lands in chat.
  // Switch the stored mode to chat *first* so the drawer doesn't linger via the
  // localStorage fallback while the (async) project scope resolves.
  const openProject = (uuid: string) => {
    localStorage.setItem('workspace:mode', 'chat')
    navigate({
      to: '/',
      search: {
        mode: undefined,
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
    if (!newName.trim()) return
    setCreating(true)
    try {
      const project = await create(newName.trim())
      setNewName('')
      openProject(project.uuid)
    } finally {
      setCreating(false)
    }
  }

  const handleDuplicate = async (p: Project) => {
    setMenuOpenId(null)
    setDuplicatingId(p.uuid)
    try {
      await duplicate(p.uuid)
      toast(`Duplicating “${p.title}” — copying files in the background`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to duplicate project', 'error')
    } finally {
      setDuplicatingId(null)
    }
  }

  return (
    <div className="relative h-full overflow-auto bg-white">
      <div className="flex items-center gap-2 border-b border-gray-200 px-5 py-4">
        <FolderKanban className="h-5 w-5 text-gray-400" />
        <h2 className="text-base font-semibold text-gray-900">Projects</h2>
        <button
          onClick={() => setShowExplainer(true)}
          className="inline-flex items-center gap-1 rounded-full border border-gray-300 px-2.5 py-1 text-[11px] font-semibold text-gray-500 hover:bg-gray-50 hover:text-gray-700"
        >
          <HelpCircle size={12} />
          What are Projects?
        </button>
        <span className="ml-auto text-xs text-gray-400">{projects.length}</span>
      </div>

      {showExplainer && <ProjectsExplainer onClose={() => setShowExplainer(false)} />}

      <div className="p-5">
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            placeholder="New project name..."
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="flex items-center gap-1 rounded-lg bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50"
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="mt-4 space-y-2">
          {loading ? (
            <div className="text-sm text-gray-500">Loading...</div>
          ) : projects.length === 0 ? (
            <ProjectsExplainer />
          ) : (
            projects.map(p => (
              <div
                key={p.uuid}
                className="group relative rounded-lg border border-gray-200 bg-white transition-colors hover:border-highlight"
              >
                <button
                  onClick={() => openProject(p.uuid)}
                  className="flex w-full flex-col items-start p-3 text-left"
                >
                  <div className="flex w-full items-center justify-between gap-2 pr-7">
                    <span className="truncate font-medium text-gray-900">{p.title}</span>
                    <ProjectStateBadge state={p.state} />
                  </div>
                  {p.description && (
                    <span className="mt-1 line-clamp-1 text-xs text-gray-500">{p.description}</span>
                  )}
                  <ProjectSummaryStats capabilities={p.capabilities} className="mt-2" />
                </button>

                {/* Per-project actions. Kept outside the card <button> above —
                    a button can't be nested inside another button. */}
                <div className="absolute right-1.5 top-1.5">
                  <button
                    onClick={() => setMenuOpenId(menuOpenId === p.uuid ? null : p.uuid)}
                    disabled={duplicatingId === p.uuid}
                    aria-label="Project actions"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 opacity-0 transition-opacity hover:bg-gray-100 hover:text-gray-600 focus:opacity-100 group-hover:opacity-100 disabled:opacity-50 disabled:cursor-wait aria-expanded:opacity-100"
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
      </div>
    </div>
  )
}
