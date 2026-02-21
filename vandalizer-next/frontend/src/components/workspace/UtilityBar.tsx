import { MessageSquare, FolderOpen, Workflow } from 'lucide-react'
import { useWorkspace, type WorkspaceMode } from '../../contexts/WorkspaceContext'

const MODES: { mode: WorkspaceMode; icon: typeof MessageSquare; label: string }[] = [
  { mode: 'chat', icon: MessageSquare, label: 'Chat' },
  { mode: 'files', icon: FolderOpen, label: 'Files' },
  { mode: 'automations', icon: Workflow, label: 'Automations' },
]

export function UtilityBar() {
  const { workspaceMode, setWorkspaceMode } = useWorkspace()

  return (
    <div
      style={{
        width: 48,
        background: '#191919',
        borderRight: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 8,
        gap: 4,
        flexShrink: 0,
      }}
    >
      {MODES.map(({ mode, icon: Icon, label }) => {
        const active = workspaceMode === mode
        return (
          <button
            key={mode}
            onClick={() => setWorkspaceMode(mode)}
            title={label}
            style={{
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: 'none',
              borderLeft: active ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
              borderRadius: 4,
              cursor: 'pointer',
              padding: 0,
            }}
          >
            <Icon
              size={20}
              style={{ color: active ? '#fff' : '#888' }}
            />
          </button>
        )
      })}
    </div>
  )
}
