import { FolderKanban, Settings, X } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { useWorkspace } from '../../contexts/WorkspaceContext'

/**
 * A thin bar shown across all workspace modes while a project scope is active.
 * It's the one project-specific chrome in the workspace — everything else
 * (files, chat, automations, knowledge) is the normal workspace, just scoped.
 */
export function ProjectContextBar() {
  const { activeProjectUuid, activeProjectTitle, activeProjectRole, deactivateProject } = useWorkspace()
  const navigate = useNavigate()
  if (!activeProjectUuid) return null
  const canManage = activeProjectRole === 'owner' || activeProjectRole === 'editor'

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 16px',
        fontSize: 13,
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
        borderBottom: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, white)',
        flexShrink: 0,
      }}
    >
      <FolderKanban size={15} style={{ color: 'var(--highlight-color, #eab308)' }} />
      <span style={{ color: '#6b7280', fontWeight: 500 }}>Project</span>
      <span style={{ color: '#111', fontWeight: 600 }}>{activeProjectTitle}</span>
      {activeProjectRole === 'viewer' && (
        <span style={{ color: '#9ca3af', fontSize: 12 }}>· viewing</span>
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        {canManage && (
          <button
            onClick={() => navigate({ to: '/projects/$uuid', params: { uuid: activeProjectUuid } })}
            title="Project settings"
            style={{ display: 'flex', alignItems: 'center', background: 'transparent', border: 'none', cursor: 'pointer', color: '#6b7280' }}
          >
            <Settings size={14} />
          </button>
        )}
        <button
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
