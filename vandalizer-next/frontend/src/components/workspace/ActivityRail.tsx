import { useCallback } from 'react'
import {
  PenSquare,
  Workflow,
  ListChecks,
  Trash2,
  PanelLeftClose,
  PanelLeftOpen,
  Zap,
  Clock,
  Settings,
  AlertTriangle,
  CircleMinus,
  CircleCheck,
  SquarePen,
} from 'lucide-react'
import { useActivities } from '../../hooks/useActivities'
import { deleteActivity } from '../../api/activity'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { cn } from '../../lib/cn'
import type { ActivityEvent } from '../../types/chat'

function activityIcon(type: ActivityEvent['type']) {
  switch (type) {
    case 'conversation':
      return PenSquare
    case 'workflow_run':
      return Workflow
    case 'search_set_run':
      return ListChecks
    default:
      return PenSquare
  }
}

function StatusIcon({ status }: { status: ActivityEvent['status'] }) {
  switch (status) {
    case 'queued':
      return <Clock className="h-3 w-3" />
    case 'running':
      return <Settings className="h-3 w-3 animate-spin" />
    case 'failed':
      return <AlertTriangle className="h-3 w-3" />
    case 'canceled':
      return <CircleMinus className="h-3 w-3" />
    case 'completed':
      return <CircleCheck className="h-3 w-3" />
    default:
      return null
  }
}

function statusMetaClass(status: ActivityEvent['status']) {
  switch (status) {
    case 'completed':
      return 'text-[#1a7f37]'
    case 'failed':
      return 'text-[#b3261e]'
    default:
      return 'text-[#0050d7]'
  }
}

export function ActivityRail() {
  const { railDocked, toggleRailDocked, setActiveRightTab, setLoadConversationId, triggerNewChat, openWorkflow, openExtraction } = useWorkspace()
  const { activities, refresh } = useActivities()

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation()
      await deleteActivity(id)
      refresh()
    },
    [refresh],
  )

  const handleClick = useCallback(
    (activity: ActivityEvent) => {
      if (activity.type === 'conversation' && activity.conversation_id) {
        setActiveRightTab('assistant')
        setLoadConversationId(activity.conversation_id)
      } else if (activity.type === 'workflow_run' && activity.workflow_id) {
        openWorkflow(activity.workflow_id)
      } else if (activity.type === 'search_set_run' && activity.search_set_uuid) {
        openExtraction(activity.search_set_uuid)
      }
    },
    [setActiveRightTab, setLoadConversationId, openWorkflow, openExtraction],
  )

  const isRunning = (status: ActivityEvent['status']) =>
    status === 'running' || status === 'queued'

  return (
    <aside
      className="flex h-full flex-col border-l border-[#d8d8d8] bg-panel-bg"
    >
      {/* Header */}
      <div className="border-b border-[#ddd]" style={{ padding: '17px 12px' }}>
        <div className="flex items-center justify-between gap-2">
          {!railDocked && (
            <div className="flex items-center gap-2">
              <Zap className="h-3.5 w-3.5" />
              <span className="text-sm font-bold">Activity</span>
            </div>
          )}
          <button
            onClick={toggleRailDocked}
            className="flex items-center justify-center rounded p-1 text-[#333] hover:bg-[#e0e0e0] hover:text-[#111] transition-colors ml-auto"
            title={railDocked ? 'Expand' : 'Collapse'}
          >
            {railDocked ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Activity list */}
      <div className="flex-1 overflow-y-auto hide-scrollbar p-2">
        <div className="flex flex-col gap-1">
          {/* New chat button - matches Flask _app_rail.html first item */}
          <div
            onClick={triggerNewChat}
            className={cn(
              'flex items-center gap-2 rounded-lg cursor-pointer p-2',
              'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
              'transition-[background-color,box-shadow] duration-200',
              railDocked ? 'justify-center' : '',
            )}
          >
            <div className="shrink-0 w-4 text-center text-[#333]">
              <SquarePen className="h-4 w-4" />
            </div>
            {!railDocked && (
              <div className="text-[11px] leading-[1.4] text-[#111]">New chat</div>
            )}
          </div>
          <div className="h-[5px]" />

          {activities.map((activity) => {
            const Icon = activityIcon(activity.type)
            const running = isRunning(activity.status)

            return (
              <div
                key={activity.id}
                onClick={() => handleClick(activity)}
                className={cn(
                  'rail-shimmer-running group relative flex items-center gap-2 rounded-lg cursor-pointer',
                  'transition-[background-color,box-shadow] duration-200',
                  railDocked ? 'justify-center p-2' : 'p-2',
                  running
                    ? 'text-white'
                    : 'hover:bg-[#f0f2f5] hover:shadow-[0_1px_3px_rgb(15_23_42/0.12)]',
                )}
                style={
                  running
                    ? {
                        background: `linear-gradient(90deg, var(--highlight-complement, #6a11cb) 0%, var(--highlight-color, #f1b300) 50%, var(--highlight-complement, #6a11cb) 100%)`,
                        backgroundSize: '200% 100%',
                        animation: 'rail-shimmer 8s linear infinite',
                      }
                    : undefined
                }
              >
                {/* Type icon */}
                <div className={cn('shrink-0 w-4 text-center', running ? 'text-white' : 'text-[#333]')}>
                  <Icon className="h-4 w-4" />
                </div>

                {!railDocked && (
                  <>
                    {/* Title + status */}
                    <div className="min-w-0 flex-1">
                      <div
                        className={cn(
                          'text-[11px] leading-[1.4] break-words',
                          running ? 'text-white' : 'text-[#111]',
                        )}
                      >
                        {activity.title || activity.type}
                      </div>
                    </div>

                    {/* Status icon */}
                    <div className={cn('shrink-0 opacity-90', running ? 'text-white' : statusMetaClass(activity.status))}>
                      <StatusIcon status={activity.status} />
                    </div>

                    {/* Delete button - appears on hover */}
                    <button
                      onClick={(e) => handleDelete(e, activity.id)}
                      className={cn(
                        'absolute right-1 top-1/2 -translate-y-1/2 z-[1]',
                        'flex items-center justify-center',
                        'rounded p-1',
                        'opacity-0 pointer-events-none',
                        'group-hover:opacity-100 group-hover:pointer-events-auto',
                        'transition-[opacity,color,background-color] duration-200',
                        'text-[#7a7f87] hover:text-[#444]',
                        running
                          ? 'bg-white/30 backdrop-blur-sm hover:bg-white/50'
                          : 'bg-white/90 backdrop-blur-sm shadow-[0_1px_3px_rgba(0,0,0,0.1)] hover:bg-white/95',
                      )}
                      title="Delete"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
