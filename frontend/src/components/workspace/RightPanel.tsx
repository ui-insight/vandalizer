import { MessageSquare, BookOpen } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { AssistantTab } from './AssistantTab'
import { LibraryTab } from './LibraryTab'
import { WorkflowEditorPanel } from './WorkflowEditorPanel'
import { ExtractionEditorPanel } from './ExtractionEditorPanel'
import { AutomationEditorPanel } from './AutomationEditorPanel'
import { cn } from '../../lib/cn'

const TABS = ['assistant', 'library'] as const

export function RightPanel() {
  const { activeRightTab, setActiveRightTab, openWorkflowId, openExtractionId, openAutomationId } = useWorkspace()

  // If an automation is open, show the automation editor instead of tabs
  if (openAutomationId) {
    return (
      <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
        <AutomationEditorPanel />
      </div>
    )
  }

  // If an extraction is open, show the extraction editor instead of tabs
  if (openExtractionId) {
    return (
      <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
        <ExtractionEditorPanel />
      </div>
    )
  }

  // If a workflow is open, show the workflow editor instead of tabs
  if (openWorkflowId) {
    return (
      <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
        <WorkflowEditorPanel />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
      {/* Tab bar - matches Flask .tab-menu */}
      <div className="flex bg-panel-dark border-b border-[#cccccc48]">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveRightTab(tab)}
            className={cn(
              'flex-1 flex items-center justify-center gap-2 py-4 text-sm cursor-pointer transition-colors',
              activeRightTab === tab
                ? 'bg-highlight text-highlight-text font-black'
                : 'text-white font-black hover:bg-[#363636]',
            )}
          >
            {tab === 'assistant' ? <><MessageSquare className="h-4 w-4" /> Assistant</> : <><BookOpen className="h-4 w-4" /> Library</>}
          </button>
        ))}
      </div>

      {/* Tab content - matches Flask .tab-content */}
      <div className="flex-1 overflow-hidden bg-white">
        {/* Keep the Assistant mounted and just hide it when Library is open, so
            the live conversation (messages, in-flight results, scroll position)
            survives a tab switch instead of being torn down and lost. Its state
            lives in ChatPanel/useChat, which reset on unmount. Library has no
            ephemeral state, so it can mount on demand. */}
        <div className={cn('h-full', activeRightTab !== 'assistant' && 'hidden')}>
          <AssistantTab />
        </div>
        {activeRightTab === 'library' && <LibraryTab />}
      </div>
    </div>
  )
}
