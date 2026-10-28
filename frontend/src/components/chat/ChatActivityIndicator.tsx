import type { ChatActivity, ToolCallInfo } from '../../types/chat'
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

/** Only fills gaps before the transcript has a thinking or running-tool entry. */
export function ChatActivityIndicator({ activity, names = {}, compactionStatus }: {
  activity?: ChatActivity | null
  names?: Record<string, string>
  compactionStatus?: string | null
}) {
  return <div className="chat-activity-line" role="status" aria-label="Assistant progress">
    <span className="chat-activity-dot" aria-hidden="true" />
    <span className="chat-activity-label">{activityLabel(activity, [], names, compactionStatus)}</span>
  </div>
}
