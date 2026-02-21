import { useEffect } from 'react'
import { useSearch, useNavigate } from '@tanstack/react-router'
import { Header } from '../layout/Header'
import { ActivityRail } from './ActivityRail'
import { PanelResizer } from './PanelResizer'
import { LeftPanel } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { UtilityBar } from './UtilityBar'
import { AutomationsPanel } from './AutomationsPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function WorkspaceLayout() {
  const { railDocked, panelSplit, openWorkflow, openExtraction, workspaceMode } = useWorkspace()
  const search = useSearch({ from: '/' })
  const navigate = useNavigate()

  // Handle deep-link query params (e.g. /?openWorkflow=123)
  useEffect(() => {
    if (search.openWorkflow) {
      openWorkflow(search.openWorkflow)
      navigate({ to: '/', search: {}, replace: true })
    } else if (search.openExtraction) {
      openExtraction(search.openExtraction)
      navigate({ to: '/', search: {}, replace: true })
    }
  }, [search, navigate, openWorkflow, openExtraction])
  const railWidth = railDocked ? 64 : 220

  const isChat = workspaceMode === 'chat'
  const isAutomations = workspaceMode === 'automations'

  // Layout: [UtilityBar 48px] [Content per mode] [ActivityRail(right)]
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <UtilityBar />
        <div
          className="flex flex-1 overflow-hidden"
          style={{
            marginRight: `${railWidth}px`,
            transition: 'margin-right 0.3s ease',
          }}
        >
          {/* Left panel area — hidden in chat mode, placeholder in automations */}
          <div
            className="overflow-hidden"
            style={{
              width: isChat ? '0%' : `${panelSplit}%`,
              minWidth: isChat ? 0 : undefined,
              transition: 'width 0.3s ease',
            }}
          >
            {isAutomations ? <AutomationsPanel /> : <LeftPanel />}
          </div>

          {/* Resizer — hidden in chat mode */}
          <div
            style={{
              opacity: isChat ? 0 : 1,
              pointerEvents: isChat ? 'none' : 'auto',
              transition: 'opacity 0.3s ease',
            }}
          >
            <PanelResizer />
          </div>

          <div className="overflow-hidden flex-1">
            <RightPanel />
          </div>
        </div>
        <div
          className="shrink-0"
          style={{
            position: 'fixed',
            top: 69,
            right: 0,
            bottom: 0,
            width: railDocked ? 64 : 'var(--rail-w)',
            zIndex: 650,
            transition: 'width 0.3s ease',
          }}
        >
          <ActivityRail />
        </div>
      </div>
    </div>
  )
}

