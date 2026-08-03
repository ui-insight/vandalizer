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

  // An open editor replaces the tab view visually, but everything underneath
  // stays mounted (hidden): the live conversation (messages, in-flight
  // results, scroll position) lives in ChatPanel/useChat and resets on
  // unmount — mid-conversation editor work (e.g. a certification module
  // built in the workflow editor) must come back to the same chat — and the
  // Library's filters, search, folder selection, and scroll likewise survive
  // opening and closing an editor.
  const editor = openAutomationId ? <AutomationEditorPanel />
    : openExtractionId ? <ExtractionEditorPanel />
    : openWorkflowId ? <WorkflowEditorPanel />
    : null

  return (
    <div className="flex h-full flex-col" style={{ boxShadow: '-7px 20px 25px -16px rgb(211, 211, 211)' }}>
      {editor && <div className="flex min-h-0 flex-1 flex-col">{editor}</div>}
      <div className={cn('flex min-h-0 flex-1 flex-col', editor && 'hidden')}>
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
          {/* Keep the Assistant mounted and just hide it when the Library tab
              is open — see the keep-mounted comment above. Library mounts on
              demand per tab switch but survives editor open/close via the
              hidden wrapper. */}
          <div className={cn('h-full', activeRightTab !== 'assistant' && 'hidden')}>
            <AssistantTab />
          </div>
          {activeRightTab === 'library' && <LibraryTab />}
        </div>
      </div>
    </div>
  )
}
