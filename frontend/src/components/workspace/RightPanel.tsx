import { RetainedPanel } from '../shared/PanelVisibility'
import { MessageSquare, BookOpen, ChevronRight, ArrowLeft } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { AssistantTab } from './AssistantTab'
import { LibraryTab } from './LibraryTab'
import { WorkflowEditorPanel } from './WorkflowEditorPanel'
import { ExtractionEditorPanel } from './ExtractionEditorPanel'
import { AutomationEditorPanel } from './AutomationEditorPanel'
import { cn } from '../../lib/cn'

const TABS = ['assistant', 'library'] as const

export function RightPanel({ hideTabs = false }: { hideTabs?: boolean }) {
  const { activeRightTab, setActiveRightTab, openWorkflowId, openExtractionId, openAutomationId, closeWorkflow, closeExtraction, closeAutomation } = useWorkspace()

  // An open editor replaces the tab view visually, but everything underneath
  // stays mounted (hidden): the live conversation (messages, in-flight
  // results, scroll position) lives in ChatPanel/useChat and resets on
  // unmount — mid-conversation editor work (e.g. a certification module
  // built in the workflow editor) must come back to the same chat — and the
  // Library's filters, search, folder selection, and scroll likewise survive
  // opening and closing an editor.
  const editor = openAutomationId ? <AutomationEditorPanel key={openAutomationId} />
    : openExtractionId ? <ExtractionEditorPanel key={openExtractionId} />
    : openWorkflowId ? <WorkflowEditorPanel key={openWorkflowId} />
    : null

  const closeEditor = openAutomationId ? closeAutomation : openExtractionId ? closeExtraction : closeWorkflow
  const editorType = openAutomationId ? 'Automation' : openExtractionId ? 'Extraction' : 'Workflow'
  const origin = activeRightTab === 'library' ? 'Library' : 'Assistant'

  return (
    <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
      {editor && <div className="flex min-h-0 flex-1 flex-col">
        <nav aria-label="Tool location" className="tool-location">
          <button type="button" onClick={closeEditor} aria-label={`Back to ${origin}`}><ArrowLeft size={14} aria-hidden="true" />{origin}</button>
          <ChevronRight size={14} aria-hidden="true" />
          <span aria-current="page">{editorType}</span>
        </nav>
        <div className="min-h-0 flex-1">{editor}</div>
      </div>}
      <div className={cn('flex min-h-0 flex-1 flex-col', editor && 'hidden')}>
        {/* Compact source modes already expose these choices above both panes. */}
        {!hideTabs && <div className="flex bg-panel-dark border-b border-[#cccccc48]">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveRightTab(tab)}
              style={{ fontSize: 'var(--workspace-font-control)' }}
              className={cn(
                'min-w-0 flex-1 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 px-1 py-3 cursor-pointer transition-colors',
                activeRightTab === tab
                  ? 'bg-highlight text-highlight-text font-black'
                  : 'text-white font-black hover:bg-[#363636]',
              )}
            >
              {tab === 'assistant' ? <><MessageSquare size={16} aria-hidden="true" /><span className="min-w-0 break-words">Assistant</span></> : <><BookOpen size={16} aria-hidden="true" /><span className="min-w-0 break-words">Library</span></>}
            </button>
          ))}
        </div>}

        {/* Tab content - matches Flask .tab-content */}
        <div className="flex-1 overflow-hidden bg-white">
          {/* Keep the Assistant mounted and just hide it when the Library tab
              is open. Visited Library content also survives tab/editor switches. */}
          <RetainedPanel active={activeRightTab === 'assistant' && !editor} eager><AssistantTab /></RetainedPanel>
          <RetainedPanel eager={activeRightTab === 'library'} active={activeRightTab === 'library' && !editor}><LibraryTab /></RetainedPanel>
        </div>
      </div>
    </div>
  )
}
