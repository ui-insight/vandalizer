import { useState } from 'react'
import { MoreVertical, Pencil, Trash2, Settings2, Users, Check } from 'lucide-react'
import type { Project, ProjectState } from '../../types/project'
import { PROJECT_STATES } from '../../types/project'
import { ProjectStateBadge } from './ProjectStateBadge'
import { ProjectSummaryStats } from './ProjectSummaryStats'

/**
 * A project card for the explorer (the /projects page). Clicking the body opens
 * the project; the ⋯ menu renames, changes status, opens the project home, or
 * deletes — so the explorer is a place you can manage projects, not just a list
 * that bounces you straight into the workspace.
 *
 * `canManage` is owner-or-editor; viewers see a read-only card with no menu.
 */
export function ProjectExplorerCard({
  project,
  canManage,
  canDelete,
  onOpen,
  onOpenHome,
  onRename,
  onSetState,
  onDelete,
}: {
  project: Project
  canManage: boolean
  canDelete: boolean
  onOpen: () => void
  onOpenHome: () => void
  onRename: (title: string) => Promise<void> | void
  onSetState: (state: ProjectState) => Promise<void> | void
  onDelete: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(project.title)

  const startRename = () => {
    setDraft(project.title)
    setEditing(true)
    setMenuOpen(false)
  }

  const commitRename = async () => {
    const t = draft.trim()
    setEditing(false)
    if (t && t !== project.title) await onRename(t)
  }

  return (
    <div className="relative flex flex-col rounded-lg border border-gray-200 bg-white p-4 text-left transition-colors hover:border-highlight">
      <div className="flex w-full items-start justify-between gap-2">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={e => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') setEditing(false)
            }}
            onClick={e => e.stopPropagation()}
            className="min-w-0 flex-1 border-b border-gray-300 bg-transparent text-sm font-medium text-gray-900 outline-none focus:border-highlight"
          />
        ) : (
          <button
            onClick={onOpen}
            className="min-w-0 flex-1 truncate text-left font-medium text-gray-900 hover:text-highlight"
            title={project.title}
          >
            {project.title}
          </button>
        )}
        <div className="flex shrink-0 items-center gap-1">
          <ProjectStateBadge state={project.state} />
          {canManage && (
            <button
              onClick={() => setMenuOpen(o => !o)}
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              title="Manage project"
              aria-label="Manage project"
            >
              <MoreVertical size={16} />
            </button>
          )}
        </div>
      </div>

      <button onClick={onOpen} className="block w-full text-left">
        {project.description && (
          <span className="mt-1 line-clamp-2 block text-sm text-gray-500">{project.description}</span>
        )}
        <div className="mt-3 flex items-center justify-between gap-3">
          <ProjectSummaryStats capabilities={project.capabilities} />
          <span className="shrink-0 text-xs text-gray-400">
            {project.team_id && (
              <span className="mr-2 inline-flex items-center gap-1">
                <Users size={12} /> Team
              </span>
            )}
            {new Date(project.updated_at).toLocaleDateString()}
          </span>
        </div>
      </button>

      {menuOpen && (
        <>
          {/* click-away backdrop */}
          <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
          <div className="absolute right-3 top-11 z-20 w-52 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
            <button
              onClick={startRename}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
            >
              <Pencil size={14} className="text-gray-400" /> Rename
            </button>
            <button
              onClick={() => { setMenuOpen(false); onOpenHome() }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
            >
              <Settings2 size={14} className="text-gray-400" /> Project settings
            </button>
            <div className="my-1 border-t border-gray-100" />
            <div className="px-3 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-gray-400">
              Status
            </div>
            {PROJECT_STATES.map(s => (
              <button
                key={s}
                onClick={() => { setMenuOpen(false); if (s !== project.state) onSetState(s) }}
                className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm capitalize text-gray-700 hover:bg-gray-50"
              >
                {s}
                {s === project.state && <Check size={14} className="text-highlight" />}
              </button>
            ))}
            {canDelete && (
              <>
                <div className="my-1 border-t border-gray-100" />
                <button
                  onClick={() => { setMenuOpen(false); onDelete() }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
                >
                  <Trash2 size={14} /> Delete
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
