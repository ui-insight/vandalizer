import { useCallback, useRef, useState } from 'react'
import { Header } from '../layout/Header'
import { ActivityRail } from './ActivityRail'
import { PanelResizer } from './PanelResizer'
import { LeftPanel } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { UtilityBar } from './UtilityBar'
import { AutomationsPanel } from './AutomationsPanel'
import { KnowledgePanel } from './KnowledgePanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { useAutomationActivity } from '../../hooks/useAutomationActivity'
import type { AutomationStarted } from '../../hooks/useAutomationActivity'
import type { CompletedAutomation } from '../../api/automations'

export function WorkspaceLayout() {
  const { railDocked, panelSplit, workspaceMode, viewDocument, setWorkspaceMode } = useWorkspace()
  const { toast } = useToast()
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleAutomationStarted = useCallback((info: AutomationStarted) => {
    toast(`${info.name} started`, 'info')
  }, [toast])

  const handleAutomationCompleted = useCallback((info: CompletedAutomation) => {
    const failed = info.status === 'failed'
    if (failed) {
      toast(`${info.name} failed`, 'error')
      return
    }
    const doc = info.documents[0]
    toast(
      `${info.name} completed`,
      'success',
      doc ? {
        label: 'Open file',
        onClick: () => {
          setWorkspaceMode('files')
          viewDocument(doc.uuid, doc.title)
        },
      } : undefined,
    )
  }, [toast, viewDocument, setWorkspaceMode])

  const automationActivity = useAutomationActivity(handleAutomationStarted, handleAutomationCompleted)

  const railWidth = railDocked ? 64 : 220

  const isChat = workspaceMode === 'chat'
  const isAutomations = workspaceMode === 'automations'
  const isKnowledge = workspaceMode === 'knowledge'

  // Layout: [UtilityBar 48px] [Content per mode] [ActivityRail(right)]
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <UtilityBar hasActiveAutomation={automationActivity.hasActive} />
        <div
          ref={containerRef}
          className="flex flex-1 overflow-hidden"
          style={{
            marginRight: `${railWidth}px`,
            transition: 'margin-right 0.3s ease',
          }}
        >
          {/* Left panel area — hidden in chat mode, drawer in automations/knowledge */}
          <div
            className="overflow-hidden"
            style={{
              width: isChat ? '0%' : `${panelSplit}%`,
              minWidth: isChat ? 0 : undefined,
              transition: isDragging ? 'none' : 'width 0.3s ease',
            }}
          >
            {isAutomations ? <AutomationsPanel activeIds={automationActivity.activeIds} /> : isKnowledge ? <KnowledgePanel /> : <LeftPanel />}
          </div>

          {/* Resizer — hidden in chat mode */}
          {!isChat && (
            <PanelResizer
              containerRef={containerRef}
              onDragStart={() => setIsDragging(true)}
              onDragEnd={() => setIsDragging(false)}
            />
          )}

          <div className="overflow-hidden flex-1 relative" style={{ zIndex: 11 }}>
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

