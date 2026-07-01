import { FolderKanban, Settings, X } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'

/**
 * A thin bar shown across all workspace modes while a project scope is active.
 * It's the one project-specific chrome in the workspace — everything else
 * (files, chat, automations, knowledge) is the normal workspace, just scoped.
 * The gear opens the in-workspace Manage panel (rename/share/leave/delete).
 */
export function ProjectContextBar({ onOpenManage }: { onOpenManage?: () => void }) {
  const { activeProjectUuid, activeProjectTitle, activeProjectRole, deactivateProject, railDocked } = useWorkspace()
  if (!activeProjectUuid) return null

  // The Activity rail is fixed to the right edge; reserve its width so the
  // Manage/Exit controls aren't rendered underneath (and unclickable).
  const railWidth = railDocked ? 64 : 220

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 16px',
        marginRight: railWidth,
        fontSize: 13,
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
        borderBottom: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, white)',
        flexShrink: 0,
      }}
    >
      <FolderKanban size={15} style={{ color: 'var(--highlight-on-light, #806600)' }} />
      <span style={{ color: '#6b7280', fontWeight: 500 }}>Project</span>
      <span style={{ color: '#111', fontWeight: 600 }}>{activeProjectTitle}</span>
      {activeProjectRole === 'viewer' && (
        <span style={{ color: '#6b7280', fontSize: 12 }}>· viewing</span>
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        {onOpenManage && (
          <button
            type="button"
            onClick={onOpenManage}
            title="View details, share, rename, leave, or delete this project"
            style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'var(--highlight-color, #eab308)', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: 'var(--highlight-text-color, #000)', fontSize: 12, fontWeight: 600 }}
          >
            <Settings size={14} />
            Manage project
          </button>
        )}
        <button
          type="button"
          onClick={deactivateProject}
          title="Exit project scope"
          style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'transparent', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 12, fontWeight: 500 }}
        >
          Exit
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
