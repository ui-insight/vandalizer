import { useEffect, useState } from 'react'
import type { ChatActivity, ToolCallInfo } from '../../types/chat'
import { isPagePreparation } from '../../lib/chatProgress'
import { activeToolLabel, getToolMeta, toolTarget } from './toolActivity'
import './chat-activity.css'

export function activityLabel(activity: ChatActivity | null | undefined, calls: ToolCallInfo[], names: Record<string, string>, compaction?: string | null): string {
  if (compaction === 'started') return 'Making room to continue'
  if (calls.length) return calls.map(call => [activeToolLabel(call), toolTarget(call, names)].filter(Boolean).join(' · ')).join('; ')
  if (activity?.phase === 'tool_preparing') {
    if (activity.tool_name === 'create_html_artifact') return 'Designing your page'
    if (activity.tool_name === 'revise_html_artifact') return 'Revising your page'
    return activity.tool_name ? `Preparing tool · ${getToolMeta(activity.tool_name).label}` : 'Preparing the next tool call'
  }
  if (activity?.phase === 'tool_running') return activity.tool_name ? getToolMeta(activity.tool_name).label : 'Using tools'
  if (activity?.phase === 'context') return activity.content || 'Preparing your context'
  if (activity?.phase === 'reviewing') return activity.tool_name ? `Reviewing results · ${getToolMeta(activity.tool_name).label}` : 'Reviewing tool results'
  if (activity?.phase === 'writing') return 'Writing your response'
  return 'Thinking'
}

function PagePreparationTimer() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [])
  // Keep live announcements on the status label, not on every timer tick.
  return <span className="chat-activity-elapsed" aria-hidden="true">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} elapsed</span>
}

/** Visible between stream updates, including while a Page's HTML is generated. */
export function ChatActivityIndicator({ activity, names = {}, compactionStatus }: {
  activity?: ChatActivity | null
  names?: Record<string, string>
  compactionStatus?: string | null
}) {
  return <div className="chat-activity-line" role="status" aria-label="Assistant progress">
    <span className="chat-activity-dot" aria-hidden="true" />
    <span className="chat-activity-label">{activityLabel(activity, [], names, compactionStatus)}</span>
    {isPagePreparation(activity) && <PagePreparationTimer key={activity?.tool_call_id || activity?.tool_name} />}
  </div>
}
