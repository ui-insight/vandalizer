import { FolderKanban, Settings, X } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

/**
 * A thin bar shown across all workspace modes while a project scope is active.
 * It's the one project-specific chrome in the workspace — everything else
 * (files, chat, automations, knowledge) is the normal workspace, just scoped.
 * The gear opens the in-workspace Manage panel (rename/share/leave/delete).
 */
export function ProjectContextBar({ onOpenManage, railWidth: fittedRailWidth }: { onOpenManage?: () => void; railWidth?: number }) {
  const { activeProjectUuid, activeProjectTitle, activeProjectRole, deactivateProject, railDocked } = useWorkspace()
  if (!activeProjectUuid) return null

  // The Activity rail is fixed to the right edge; reserve its width so the
  // Manage/Exit controls aren't rendered underneath (and unclickable).
  const railWidth = fittedRailWidth ?? (railDocked ? 64 : 220)

  return (
    <div
      role="region" aria-label="Active project"
      className="project-context-bar"
      style={{
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 'var(--workspace-space-8)',
        padding: "var(--workspace-space-6) var(--workspace-space-16)",
        marginRight: railWidth,
        fontSize: 'var(--workspace-font-control)',
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
        borderBottom: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, white)',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', flex: '1 1 240px', minWidth: 0 }}>
        <FolderKanban size={15} style={{ color: 'var(--highlight-on-light, #806600)', flexShrink: 0 }} />
        <span className="project-context-label" style={{ color: '#59616b', fontWeight: 500 }}>Project</span>
        <span style={{ color: '#111', fontWeight: 600, minWidth: 0, overflowWrap: 'anywhere', flex: 1 }}>{activeProjectTitle}</span>
        {activeProjectRole === 'viewer' && (
          <span style={{ color: '#59616b', fontSize: 'var(--workspace-font-meta)' }}>Read only</span>
        )}
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)', flexShrink: 0 }}>
        {onOpenManage && (
          <button
            type="button"
            onClick={onOpenManage}
            title="View details, share, rename, leave, or delete this project"
            style={{ minHeight: 'var(--workspace-control-height)', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', background: 'var(--highlight-color, #eab308)', border: 'none', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-4) var(--workspace-space-12)", cursor: 'pointer', color: 'var(--highlight-text-color, #000)', fontSize: 'var(--workspace-font-meta)', fontWeight: 600 }}
          >
            <Settings size={14} />
            Manage project
          </button>
        )}
        <button
          type="button"
          onClick={deactivateProject}
          title="Exit project scope"
          style={{ minHeight: 'var(--workspace-control-height)', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-4)', background: 'transparent', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 'var(--workspace-font-meta)', fontWeight: 500 }}
        >
          Exit
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
