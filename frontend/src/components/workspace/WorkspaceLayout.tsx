import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, X } from 'lucide-react'
import { Header } from '../layout/Header'
import { ActivityRail } from './ActivityRail'
import { PanelResizer } from './PanelResizer'
import { LeftPanel } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { UtilityBar } from './UtilityBar'
import { ProjectContextBar } from './ProjectContextBar'
import { ProjectManageModal } from './ProjectManageModal'
import { ProjectsPanel } from './ProjectsPanel'
import { AutomationsPanel } from './AutomationsPanel'
import { KnowledgePanel } from './KnowledgePanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useToast } from '../../contexts/ToastContext'
import { useAutomationActivity } from '../../hooks/useAutomationActivity'
import type { AutomationStarted } from '../../hooks/useAutomationActivity'
import type { CompletedAutomation } from '../../api/automations'

export function WorkspaceLayout() {
  const { railDocked, panelSplit, chatSplitOpen, workspaceMode, viewDocument, setWorkspaceMode, activeProjectUuid } = useWorkspace()
  const { toast } = useToast()
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const [isCompact, setIsCompact] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)

  useEffect(() => {
    const query = window.matchMedia('(max-width: 767px)')
    const updateCompactMode = () => {
      setIsCompact(query.matches)
      if (!query.matches) setActivityOpen(false)
    }
    updateCompactMode()
    query.addEventListener('change', updateCompactMode)
    return () => query.removeEventListener('change', updateCompactMode)
  }, [])

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

  // Once a project is scoped, the workspace shows that project (chat/files/…) —
  // the Projects drawer (the picker) must not linger underneath it.
  const isProjects = workspaceMode === 'projects' && !activeProjectUuid
  const isChat = workspaceMode === 'chat' || (workspaceMode === 'projects' && !!activeProjectUuid)
  // Chat normally runs full-width, but the user can open the file browser
  // beside it (split view) — e.g. to work through the certification program
  // with their documents in sight.
  // On narrow screens, a desktop split makes both sides unusably thin. Chat
  // remains the full-width right panel; every other workspace mode uses its
  // purpose-built left panel as the full mobile view.
  const showLeftOnly = isCompact && !isChat
  const collapseLeft = !showLeftOnly && isChat && !chatSplitOpen
  const isAutomations = workspaceMode === 'automations'
  const isKnowledge = workspaceMode === 'knowledge'
  const railWidth = isCompact ? 0 : railDocked ? 64 : 220
  const workspaceHeading = isChat
    ? 'Assistant workspace'
    : isProjects
      ? 'Projects workspace'
      : isAutomations
        ? 'Automations workspace'
        : isKnowledge
          ? 'Knowledge workspace'
          : 'Files workspace'

  // Layout: [UtilityBar 48px] [Content per mode] [ActivityRail(right)]
  return (
    <div className="flex h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg focus:ring-2 focus:ring-highlight"
      >
        Skip to main content
      </a>
      <Header />
      <ProjectContextBar onOpenManage={() => setManageOpen(true)} />
      <ProjectManageModal open={manageOpen} onClose={() => setManageOpen(false)} />
      <h1 className="sr-only">{workspaceHeading}</h1>
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
          {/* Left panel area — hidden in chat mode (unless split view is open),
              drawer in automations/knowledge */}
          <div
            className="overflow-hidden"
            style={{
              width: collapseLeft ? '0%' : showLeftOnly ? '100%' : `${panelSplit}%`,
              minWidth: collapseLeft ? 0 : undefined,
              transition: isDragging ? 'none' : 'width 0.3s ease',
            }}
          >
            {isProjects ? <ProjectsPanel /> : isAutomations ? <AutomationsPanel activeIds={automationActivity.activeIds} /> : isKnowledge ? <KnowledgePanel /> : <LeftPanel />}
          </div>

          {/* Resizer — hidden when the left panel is collapsed */}
          {!collapseLeft && !showLeftOnly && (
            <PanelResizer
              containerRef={containerRef}
              onDragStart={() => setIsDragging(true)}
              onDragEnd={() => setIsDragging(false)}
            />
          )}

          <main id="main-content" className={showLeftOnly ? 'hidden' : 'overflow-hidden flex-1 relative'} style={{ zIndex: 11 }}>
            <RightPanel />
          </main>
        </div>
        {isCompact && activityOpen && (
          <button
            type="button"
            aria-label="Close activity"
            className="fixed inset-0 top-[69px] z-[640] cursor-default bg-black/30"
            onClick={() => setActivityOpen(false)}
          />
        )}
        {isCompact && !activityOpen && (
          <button
            type="button"
            aria-label="Open activity"
            className="fixed right-3 top-[81px] z-[630] flex h-10 w-10 items-center justify-center rounded-full border border-[#d2d2d2] bg-white text-[#303030] shadow-md transition-colors hover:bg-[#f0f2f5] focus:outline-none focus:ring-2 focus:ring-highlight"
            onClick={() => setActivityOpen(true)}
          >
            <Activity className="h-4 w-4" />
          </button>
        )}
        <div
          aria-label={isCompact ? 'Activity' : undefined}
          aria-modal={isCompact || undefined}
          className="shrink-0"
          role={isCompact ? 'dialog' : undefined}
          style={{
            position: 'fixed',
            top: 69,
            right: 0,
            bottom: 0,
            width: isCompact ? 'min(320px, calc(100vw - 48px))' : railDocked ? 64 : 'var(--rail-w)',
            zIndex: 650,
            transition: 'width 0.3s ease, transform 0.25s ease',
            transform: isCompact && !activityOpen ? 'translateX(100%)' : undefined,
            visibility: isCompact && !activityOpen ? 'hidden' : undefined,
          }}
        >
          {isCompact && (
            <button
              type="button"
              aria-label="Close activity"
              className="absolute right-3 top-3 z-10 flex h-7 w-7 items-center justify-center rounded-md text-[#333] hover:bg-[#e0e0e0] focus:outline-none focus:ring-2 focus:ring-highlight"
              onClick={() => setActivityOpen(false)}
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <ActivityRail forceExpanded={isCompact} />
        </div>
      </div>
    </div>
  )
}
