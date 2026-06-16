import { FolderKanban, Sparkles, X } from 'lucide-react'
import { useProject } from '../../hooks/useProjects'
import { ProjectStateBadge } from '../projects/ProjectStateBadge'

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
  const title = project?.title ?? fallbackTitle ?? 'Project'
  const kbReady = project?.capabilities?.knowledge.ready

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 16px',
        fontSize: 12,
        fontWeight: 600,
        color: 'var(--highlight-color, #eab308)',
        backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
        borderTop: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)',
      }}
    >
      <FolderKanban size={14} />
      <span>Project: {title}</span>
      {project?.state && <ProjectStateBadge state={project.state} />}
      {kbReady && (
        <span
          title="Answers are grounded in this project's knowledge base"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 3, opacity: 0.75, fontWeight: 500 }}
        >
          <Sparkles size={12} /> grounded in project KB
        </span>
      )}
      <span style={{ flex: 1 }} />
      <button
        onClick={onExit}
        title="Exit project scope"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: 2,
          display: 'flex',
          color: 'inherit',
          opacity: 0.7,
        }}
      >
        <X size={14} />
      </button>
    </div>
  )
}
