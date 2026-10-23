import { useState } from 'react'
import { MessageSquare, FolderOpen, Workflow, BookOpen, FolderKanban, PanelLeftOpen, PanelLeftClose } from 'lucide-react'
import { useWorkspace, type WorkspaceMode } from '../../contexts/WorkspaceContext'

const MODES: { mode: WorkspaceMode; icon: typeof MessageSquare; label: string }[] = [
  { mode: 'chat', icon: MessageSquare, label: 'Chat' },
  { mode: 'files', icon: FolderOpen, label: 'Files' },
  { mode: 'automations', icon: Workflow, label: 'Automations' },
  { mode: 'knowledge', icon: BookOpen, label: 'Knowledge' },
]

export function UtilityBar({ hasActiveAutomation = false }: { hasActiveAutomation?: boolean }) {
  const { workspaceMode, setWorkspaceMode, activeProjectRole, activeProjectUuid, deactivateProject } = useWorkspace()
  const [showLabels, setShowLabels] = useState(false)
  // The Projects icon shows the picker, which is exclusive with being scoped
  // into a project — so it's "active" only when a project is NOT scoped.
  const activeMode = workspaceMode === 'projects' && activeProjectUuid ? 'chat' : workspaceMode
  const projectsActive = workspaceMode === 'projects' && !activeProjectUuid
  // A shared-in viewer (e.g. a PI) gets chat only — no files/automations/knowledge.
  const modes = activeProjectRole === 'viewer' ? MODES.filter(m => m.mode === 'chat') : MODES

  return (
    <nav
      aria-label="Workspace navigation"
      className={`workspace-utility${showLabels ? ' workspace-utility--expanded' : ''}`}
      style={{
        width: 88,
        background: 'var(--color-panel-dark)',
        borderRight: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 'var(--workspace-space-8)',
        gap: 'var(--workspace-space-4)',
        flexShrink: 0,
      }}
    >
      <button type="button" className="workspace-utility-toggle" aria-label={showLabels ? 'Hide navigation labels' : 'Show navigation labels'} aria-expanded={showLabels} onClick={() => setShowLabels(value => !value)}>
        {showLabels ? <PanelLeftClose size={20} aria-hidden="true" /> : <PanelLeftOpen size={20} aria-hidden="true" />}
      </button>
      {/* Projects — drops any active project scope and shows the project picker
          (the drawer). Being scoped into a project is exclusive with the list. */}
      <button
        onClick={() => { deactivateProject(); setWorkspaceMode('projects') }}
        title="Projects"
        aria-label="Projects"
        aria-current={projectsActive ? 'page' : undefined}
        style={{
          width: 80,
          minHeight: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 4,
          background: 'transparent',
          border: 'none',
          borderLeft: projectsActive ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
          borderRadius: 'var(--workspace-radius-small)',
          cursor: 'pointer',
          padding: 0,
        }}
      >
        <FolderKanban size={20} style={{ color: projectsActive ? '#fff' : '#b6bdc7' }} />
        <span className="workspace-utility-label" style={{ fontSize: 12, color: projectsActive ? '#fff' : '#b6bdc7' }}>Projects</span>
      </button>
      <div style={{ width: 24, height: 1, background: '#333', margin: "var(--workspace-space-2) 0 var(--workspace-space-4)" }} />

      {modes.map(({ mode, icon: Icon, label }) => {
        const active = activeMode === mode
        const isAutomations = mode === 'automations'
        const showPulse = isAutomations && hasActiveAutomation && active
        const showDot = isAutomations && hasActiveAutomation && !active
        return (
          <button
            key={mode}
            onClick={() => setWorkspaceMode(mode)}
            title={label}
            aria-label={label}
            aria-current={active ? 'page' : undefined}
            style={{
              position: 'relative',
              width: 80,
              minHeight: 56,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
          flexDirection: 'column',
          gap: 4,
              background: 'transparent',
              border: 'none',
              borderLeft: active ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
              borderRadius: 'var(--workspace-radius-small)',
              cursor: 'pointer',
              padding: 0,
              animation: showPulse ? 'automationGlow 2s ease-in-out infinite' : undefined,
            }}
          >
            <Icon
              size={20}
              style={{ color: (isAutomations && hasActiveAutomation) ? 'var(--highlight-color, #eab308)' : active ? '#fff' : '#b6bdc7' }}
            />
            <span className="workspace-utility-label" style={{ fontSize: 12, color: active ? '#fff' : '#b6bdc7' }}>{label}</span>
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
    </nav>
  )
}
