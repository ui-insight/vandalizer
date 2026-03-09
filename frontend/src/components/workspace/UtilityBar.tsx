import { MessageSquare, FolderOpen, Workflow, BookOpen } from 'lucide-react'
import { useWorkspace, type WorkspaceMode } from '../../contexts/WorkspaceContext'
import { useAutomationActivity } from '../../hooks/useAutomationActivity'

const MODES: { mode: WorkspaceMode; icon: typeof MessageSquare; label: string }[] = [
  { mode: 'chat', icon: MessageSquare, label: 'Chat' },
  { mode: 'files', icon: FolderOpen, label: 'Files' },
  { mode: 'automations', icon: Workflow, label: 'Automations' },
  { mode: 'knowledge', icon: BookOpen, label: 'Knowledge' },
]

export function UtilityBar() {
  const { workspaceMode, setWorkspaceMode, resetToHome } = useWorkspace()
  const { hasActive } = useAutomationActivity()

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
        const isAutomations = mode === 'automations'
        const showPulse = isAutomations && hasActive && active
        const showDot = isAutomations && hasActive && !active
        return (
          <button
            key={mode}
            onClick={() => {
              if (mode === 'chat' && active) {
                resetToHome()
              } else {
                setWorkspaceMode(mode)
              }
            }}
            title={label}
            style={{
              position: 'relative',
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
              animation: showPulse ? 'automationGlow 2s ease-in-out infinite' : undefined,
            }}
          >
            <Icon
              size={20}
              style={{ color: (isAutomations && hasActive) ? 'var(--highlight-color, #eab308)' : active ? '#fff' : '#888' }}
            />
            {showDot && (
              <span
                style={{
                  position: 'absolute',
                  top: 6,
                  right: 4,
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  backgroundColor: 'var(--highlight-color, #eab308)',
                  animation: 'automationDot 1.5s ease-in-out infinite',
                }}
              />
            )}
          </button>
        )
      })}

      <style>{`
        @keyframes automationGlow {
          0%, 100% { box-shadow: 0 0 4px rgba(234, 179, 8, 0.2); }
          50% { box-shadow: 0 0 12px rgba(234, 179, 8, 0.6); }
        }
        @keyframes automationDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </div>
  )
}
