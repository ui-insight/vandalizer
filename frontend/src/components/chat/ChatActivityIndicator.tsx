import { useId, useState } from 'react'
import { ArrowUpRight, Check, ChevronDown, CirclePause, Loader2, TriangleAlert } from 'lucide-react'
import type { ChatActivity, StreamSegment, ToolCallInfo, ToolResultInfo } from '../../types/chat'
import { activeToolLabel, getToolMeta, toolOutcome, toolTarget } from './toolActivity'
import './chat-activity.css'

function activityLabel(activity: ChatActivity | null | undefined, calls: ToolCallInfo[], compaction?: string | null): string {
  if (compaction === 'started') return 'Making room to continue'
  if (calls.length) return calls.length > 1 ? `${calls.length} tools working in parallel` : activeToolLabel(calls[0])
  if (activity?.phase === 'tool_preparing') {
    if (activity.tool_name === 'create_html_artifact') return 'Designing your page'
    if (activity.tool_name === 'revise_html_artifact') return 'Revising your page'
    return 'Preparing the next tool call'
  }
  if (activity?.phase === 'tool_running') return activity.tool_name ? getToolMeta(activity.tool_name).label : 'Using tools'
  if (activity?.phase === 'context') return 'Preparing your context'
  if (activity?.phase === 'reviewing') return 'Reviewing tool results'
  if (activity?.phase === 'writing') return 'Writing your response'
  return 'Thinking'
}

export function ChatActivityIndicator({ activity, calls = [], results = [], segments = [], names = {}, compactionStatus }: {
  activity?: ChatActivity | null
  calls?: ToolCallInfo[]
  results?: ToolResultInfo[]
  segments?: StreamSegment[]
  names?: Record<string, string>
  compactionStatus?: string | null
}) {
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const label = activityLabel(activity, calls, compactionStatus)
  const callMap = new Map<string, ToolCallInfo>()
  for (const segment of segments) if (segment.kind === 'tool_call') callMap.set(segment.call.tool_call_id, segment.call)
  for (const call of calls) callMap.set(call.tool_call_id, call)
  for (const result of results) if (!callMap.has(result.tool_call_id)) callMap.set(result.tool_call_id, { ...result, args: {} })
  const resultMap = new Map(results.map(result => [result.tool_call_id, result]))
  const activeIds = new Set(calls.map(call => call.tool_call_id))
  return <section className="chat-activity" aria-label="Live assistant activity">
    <div className="chat-activity-line">
      <span className="chat-activity-dot" aria-hidden="true" />
      <span className="chat-activity-label" role="status" aria-live="polite" aria-atomic="true">{label}</span>
      {callMap.size > 0 && <button type="button" aria-label={expanded ? 'Hide tool activity' : 'Show tool activity'} aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded(value => !value)} className="chat-activity-toggle"><ChevronDown size={14} className={expanded ? 'is-expanded' : ''} aria-hidden="true" /></button>}
    </div>
    {expanded && callMap.size > 0 && <ol id={detailsId} className="chat-activity-steps" aria-label="Tool activity this turn">
      {[...callMap.values()].map(call => {
        const result = resultMap.get(call.tool_call_id)
        const outcome = result ? toolOutcome(result) : null
        const active = activeIds.has(call.tool_call_id)
        const Icon = active ? Loader2 : outcome === 'error' ? TriangleAlert : outcome === 'approval' || outcome === 'canceled' ? CirclePause : result ? Check : ArrowUpRight
        const status = active ? 'Running' : outcome === 'error' ? 'Needs attention' : outcome === 'approval' ? 'Awaiting approval' : outcome === 'canceled' ? 'Canceled' : result ? 'Response received' : 'Awaiting response'
        return <li key={call.tool_call_id} data-state={active ? 'active' : outcome || 'pending'}><Icon size={14} aria-hidden="true" className={active ? 'chat-activity-spin' : ''} /><div><strong>{active ? activeToolLabel(call) : getToolMeta(call.tool_name).label}</strong>{toolTarget(call, names) && <span>{toolTarget(call, names)}</span>}</div><small>{status}</small></li>
      })}
    </ol>}
  </section>
}
