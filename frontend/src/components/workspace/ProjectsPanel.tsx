import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Plus, FolderKanban } from 'lucide-react'
import { useProjects } from '../../hooks/useProjects'
import { ProjectStateBadge } from '../projects/ProjectStateBadge'
import { ProjectSummaryStats } from '../projects/ProjectSummaryStats'
import { ProjectsExplainer } from '../projects/ProjectsExplainer'

/**
 * The Projects drawer — a slideout panel (like Automations/Knowledge) listing
 * the user's projects. Clicking one drops you into the scoped workspace; this
 * panel never hosts project tools, it just gets you into a project.
 */
export function ProjectsPanel() {
  const navigate = useNavigate()
  const { projects, loading, create } = useProjects()
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const enter = (uuid: string) =>
    navigate({
      to: '/',
      search: {
        mode: 'files',
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
        project: uuid,
        workflow_share_token: undefined,
      },
    })

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const project = await create(newName.trim())
      setNewName('')
      enter(project.uuid)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="h-full overflow-auto bg-white">
      <div className="flex items-center gap-2 border-b border-gray-200 px-5 py-4">
        <FolderKanban className="h-5 w-5 text-gray-400" />
        <h2 className="text-base font-semibold text-gray-900">Projects</h2>
        <span className="ml-auto text-xs text-gray-400">{projects.length}</span>
      </div>

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
              <button
                key={p.uuid}
                onClick={() => enter(p.uuid)}
                className="flex w-full flex-col items-start rounded-lg border border-gray-200 bg-white p-3 text-left hover:border-highlight transition-colors"
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="truncate font-medium text-gray-900">{p.title}</span>
                  <ProjectStateBadge state={p.state} />
                </div>
                {p.description && (
                  <span className="mt-1 line-clamp-1 text-xs text-gray-500">{p.description}</span>
                )}
                <ProjectSummaryStats capabilities={p.capabilities} className="mt-2" />
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
