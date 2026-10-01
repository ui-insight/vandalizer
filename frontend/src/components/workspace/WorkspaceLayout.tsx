import { InputReadinessNotice } from './InputReadinessNotice'
import { RetainedPanel } from '../shared/PanelVisibility'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { fitPanelSplit, panelSplitBounds, readCompactPanelChoices, saveCompactPanelChoices } from '../../utils/workspaceLayout'
import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
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
  const { railDocked, panelSplit, chatSplitOpen, workspaceMode, viewDocument, setWorkspaceMode, activeProjectUuid, openAutomationId, openWorkflowId, openExtractionId, focusChatSignal, activeRightTab, setActiveRightTab } = useWorkspace()
  const { toast } = useToast()
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const [isCompact, setIsCompact] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const activityNavigating = useRef(false)
  const openActivity = () => { activityNavigating.current = false; setActivityOpen(true) }
  useEffect(() => {
    if (activityOpen || !activityNavigating.current) return
    const frame = requestAnimationFrame(() => {
      document.querySelector<HTMLElement>('[aria-label="Tools and assistant"]')?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [activityOpen])
  const [panelChoices, setPanelChoices] = useState(readCompactPanelChoices)
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const choosePanel = useCallback((mode: string, panel: 'source' | 'tools') => {
    setPanelChoices(previous => {
      const next = { ...previous, [mode]: panel }
      saveCompactPanelChoices(next)
      return next
    })
  }, [])
  useEffect(() => {
    const resize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  const previousFocus = useRef(focusChatSignal)
  useEffect(() => {
    if (previousFocus.current === focusChatSignal) return
    previousFocus.current = focusChatSignal
    choosePanel(workspaceMode, 'tools')
  }, [focusChatSignal, workspaceMode, choosePanel])

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
  const hasEditor = !!(openAutomationId || openWorkflowId || openExtractionId)
  const editorKey = openAutomationId ? `automation:${openAutomationId}` : openWorkflowId ? `workflow:${openWorkflowId}` : openExtractionId ? `extraction:${openExtractionId}` : null
  const previousEditor = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (previousEditor.current === editorKey) return
    const wasMounted = previousEditor.current !== undefined
    previousEditor.current = editorKey
    if (editorKey && (wasMounted || !panelChoices[workspaceMode])) choosePanel(workspaceMode, 'tools')
  }, [editorKey, workspaceMode, choosePanel, panelChoices])
  const assistantOpen = panelChoices[workspaceMode] === 'tools'
  // Desktop keeps files/section content alongside the Library and its tools.
  // Compact screens switch panes without discarding the open file or editor.
  const showLeftOnly = isCompact && !isChat && !assistantOpen
  const collapseLeft = (isChat && (!chatSplitOpen || isCompact)) || (isCompact && assistantOpen)
  const isAutomations = workspaceMode === 'automations'
  const isKnowledge = workspaceMode === 'knowledge'
  const autoDockRail = !isCompact && viewportWidth < 1100
  const drawerOpen = (isCompact || autoDockRail) && activityOpen
  const railWidth = isCompact ? 0 : railDocked || autoDockRail ? 64 : 220
  const availableWidth = Math.max(1, viewportWidth - 88 - railWidth - 6)
  const visibleSplit = fitPanelSplit(panelSplit, availableWidth)
  const splitBounds = panelSplitBounds(availableWidth)
  useEffect(() => { setActivityOpen(false) }, [isCompact, autoDockRail])
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
    <div className="workspace-shell flex h-screen min-w-0 flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-lg focus:ring-2 focus:ring-highlight"
      >
        Skip to main content
      </a>
      <Header onOpenActivity={isCompact ? openActivity : undefined} />
      <ProjectContextBar railWidth={railWidth} onOpenManage={() => setManageOpen(true)} />
      <ProjectManageModal key={activeProjectUuid ?? 'no-project'} open={manageOpen} onClose={() => setManageOpen(false)} />
      <h1 className="sr-only">{workspaceHeading}</h1>
      <div className="flex flex-1 overflow-hidden">
        <UtilityBar hasActiveAutomation={automationActivity.hasActive} />
        <main id="main-content"
          ref={containerRef}
          className="flex min-w-0 flex-1 flex-col overflow-hidden relative"
          style={{
            marginRight: `${railWidth}px`,
            transition: 'margin-right 0.3s ease',
          }}
        >
          {isCompact && !isChat && (
            <div role="group" aria-label="Workspace panels" className="flex shrink-0 flex-wrap gap-1 border-b border-gray-200 bg-white p-2">
              <button type="button" aria-label={isProjects ? 'Projects panel' : isAutomations ? 'Automations panel' : isKnowledge ? 'Knowledge panel' : 'Files panel'} aria-pressed={showLeftOnly} onClick={() => choosePanel(workspaceMode, 'source')} className="rounded border border-gray-300 px-2 py-2 text-sm aria-pressed:bg-gray-900 aria-pressed:text-white">
                {isProjects ? 'Projects' : isAutomations ? 'Automations' : isKnowledge ? 'Knowledge' : 'Files'}
              </button>
              <button type="button" aria-label={hasEditor ? 'Open tool panel' : 'Open Library panel'} aria-pressed={!showLeftOnly && (hasEditor || activeRightTab === 'library')} onClick={() => { choosePanel(workspaceMode, 'tools'); if (!hasEditor) setActiveRightTab('library') }} className="rounded border border-gray-300 px-2 py-2 text-sm aria-pressed:bg-gray-900 aria-pressed:text-white">
                {hasEditor ? 'Tool' : 'Library'}
              </button>
              {!hasEditor && <button type="button" aria-label="Open Assistant panel" aria-pressed={!showLeftOnly && activeRightTab === 'assistant'} onClick={() => { choosePanel(workspaceMode, 'tools'); setActiveRightTab('assistant') }} className="rounded border border-gray-300 px-2 py-2 text-sm aria-pressed:bg-gray-900 aria-pressed:text-white">Assistant</button>}
            </div>
          )}
          <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
          {/* Left panel area — hidden in chat mode (unless split view is open),
              drawer in automations/knowledge */}
          <div
            id="workspace-source-pane"
            role="region"
            aria-label="Workspace source panel"
            className="overflow-hidden"
            style={{
              width: collapseLeft ? '0%' : showLeftOnly ? '100%' : `calc(${visibleSplit}% - ${6 * visibleSplit / 100}px)`,
              minWidth: 0,
              display: collapseLeft ? 'none' : undefined,
              transition: isDragging ? 'none' : 'width 0.3s ease',
            }}
          >
            <RetainedPanel eager active={!isProjects && !isAutomations && !isKnowledge && !collapseLeft}><LeftPanel /></RetainedPanel>
            <RetainedPanel active={isProjects && !collapseLeft}><ProjectsPanel /></RetainedPanel>
            <RetainedPanel key={`automations:${activeProjectUuid ?? 'all'}`} active={isAutomations && !collapseLeft}><AutomationsPanel activeIds={automationActivity.activeIds} /></RetainedPanel>
            <RetainedPanel key={`knowledge:${activeProjectUuid ?? 'all'}`} active={isKnowledge && !collapseLeft}><KnowledgePanel /></RetainedPanel>
          </div>

          {/* Resizer — hidden when the left panel is collapsed */}
          {!collapseLeft && !showLeftOnly && (
            <PanelResizer
              containerRef={containerRef}
              value={visibleSplit}
              min={splitBounds.min}
              max={splitBounds.max}
              onDragStart={() => setIsDragging(true)}
              onDragEnd={() => setIsDragging(false)}
            />
          )}

          <div role="region" tabIndex={-1} aria-label="Tools and assistant" className={showLeftOnly ? 'hidden' : 'overflow-hidden min-w-0 flex-1 relative flex flex-col'} style={{ zIndex: 11 }}>
            <InputReadinessNotice />
            <div style={{ flex: 1, minHeight: 0 }}><RetainedPanel eager active={!showLeftOnly}><RightPanel hideTabs={isCompact && !isChat} /></RetainedPanel></div>
          </div>
          </div>
        </main>
        {drawerOpen && (
          <button
            type="button"
            aria-label="Close activity"
            className="fixed inset-0 z-[640] cursor-default bg-black/30"
            onClick={() => setActivityOpen(false)}
          />
        )}
        <FocusTrap active={drawerOpen} focusTrapOptions={{ initialFocus: () => document.querySelector<HTMLElement>('[data-activity-return="true"]') ?? document.getElementById('close-workspace-activity')!, escapeDeactivates: false, allowOutsideClick: true, setReturnFocus: node => activityNavigating.current ? false : node, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
        <div
          aria-label={drawerOpen ? 'Activity' : undefined}
          aria-modal={drawerOpen || undefined}
          className="shrink-0"
          role={drawerOpen ? 'dialog' : undefined}
          onKeyDown={event => { if (drawerOpen && event.key === 'Escape') { event.stopPropagation(); setActivityOpen(false) } }}
          style={{
            position: 'fixed',
            top: 69,
            right: 0,
            bottom: 0,
            width: drawerOpen || isCompact ? 'min(320px, calc(100vw - 48px))' : railWidth,
            zIndex: 650,
            transition: 'width 0.3s ease, transform 0.25s ease',
            transform: isCompact && !activityOpen ? 'translateX(100%)' : undefined,
            visibility: isCompact && !activityOpen ? 'hidden' : undefined,
          }}
        >
          {drawerOpen && (
            <button
              id="close-workspace-activity"
              type="button"
              aria-label="Close activity"
              className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-md text-[#333] hover:bg-[#e0e0e0] focus:outline-none focus:ring-2 focus:ring-highlight"
              onClick={() => setActivityOpen(false)}
            >
              <X className="h-4 w-4" />
            </button>
          )}
          <ActivityRail forceExpanded={drawerOpen} forceDocked={autoDockRail} onExpand={openActivity} onNavigate={() => { activityNavigating.current = true; setActivityOpen(false) }} />
        </div>
        </FocusTrap>
      </div>
    </div>
  )
}
