import { useState } from 'react'
import { PageDialog } from '../artifacts/PagePrimitives'
import { BookOpen, LogOut } from 'lucide-react'
import { useProject } from '../../hooks/useProjects'

/**
 * A chat-anchored chip shown above the input while a project is active. It tells
 * the user "this conversation is scoped to the project, grounded in its
 * knowledge base" — complementary to the workspace-level ProjectContextBar.
 *
 * The `useProject` query lives inside this small component (not in ChatPanel) so
 * its loading/refetch transitions don't re-render the whole chat panel. It
 * usually paints instantly from the react-query cache the project pages warm.
 */
export function ProjectChatBadge({
  projectUuid,
  fallbackTitle,
  onExit,
}: {
  projectUuid: string
  fallbackTitle: string | null
  onExit: () => void
}) {
  const { project } = useProject(projectUuid)
  const [viewingContext, setViewingContext] = useState(false)
  const title = project?.title ?? fallbackTitle ?? 'Project'
  const knowledge = project?.capabilities?.knowledge
  const sourceStatus = !project ? 'Checking availability…'
    : project.capabilities.files?.count === 0 && knowledge?.documents === 0 ? 'No documents yet'
    : !knowledge?.ready ? 'Knowledge not ready'
    : knowledge.documents === 0 ? 'No documents indexed yet'
    : `Knowledge available${knowledge.documents != null ? ` · ${knowledge.documents} indexed document${knowledge.documents === 1 ? '' : 's'}` : ''}`

  return (
    <div className="project-source-bar">
      <BookOpen size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
      <div className="project-source-copy" style={{ display: 'flex', flexWrap: 'wrap', gap: "var(--workspace-space-2) var(--workspace-space-8)", minWidth: 0 }}>
        <span className="project-source-title" title={`Sources for ${title}`}>Project sources</span>
        <span style={{ fontWeight: 400 }}>{sourceStatus}</span>
        {project?.context && <button type="button" className="min-h-9 rounded border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700" onClick={() => setViewingContext(true)} aria-label="View project context">Project context on</button>}
      </div>
      {viewingContext && project?.context && <PageDialog title="Project context" onClose={() => setViewingContext(false)}><p>Saved guidance for <strong>{title}</strong>. Your current request takes precedence. Edit this brief in Manage project.</p><p className="whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-4">{project.context}</p></PageDialog>}
      <button
        onClick={onExit}
        title="Exit project scope"
        aria-label="Exit project scope"
        className="project-source-exit"
      >
        <LogOut size={14} aria-hidden="true" /> Exit project
      </button>
    </div>
  )
}
