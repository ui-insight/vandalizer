import { BookOpen, X } from 'lucide-react'
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
  const title = project?.title ?? fallbackTitle ?? 'Project'
  const kbReady = project?.capabilities?.knowledge.ready

  return (
    <div
      style={{
        display: 'grid',
        flexShrink: 0,
        gridTemplateColumns: '14px minmax(0, 1fr) 36px',
        alignItems: 'center',
        gap: 'var(--workspace-space-8)',
        padding: "var(--workspace-space-6) var(--workspace-space-16)",
        fontSize: 'var(--workspace-font-meta)',
        fontWeight: 600,
        color: '#424a55',
        backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
        borderTop: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, white)',
      }}
    >
      <BookOpen size={14} aria-hidden="true" style={{ flexShrink: 0 }} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: "var(--workspace-space-2) var(--workspace-space-8)", minWidth: 0 }}>
        <span title={`Sources for ${title}`}>Project sources</span>
        <span style={{ fontWeight: 400 }}>{project ? kbReady ? 'Knowledge available' : 'Knowledge not ready' : 'Checking availability…'}</span>
      </div>
      <button
        onClick={onExit}
        title="Exit project scope"
        aria-label="Exit project scope"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          minWidth: 36, minHeight: 'var(--workspace-control-height)', alignItems: 'center', justifyContent: 'center', padding: 'var(--workspace-space-2)',
          display: 'flex',
          color: 'inherit',
          opacity: 1,
        }}
      >
        <X size={14} />
      </button>
    </div>
  )
}
