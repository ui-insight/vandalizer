import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUpRight, Check, ChevronDown, CirclePause, Clock3, Loader2, Sparkles, TriangleAlert } from 'lucide-react'
import type { ChatActivity, StreamSegment, ToolCallInfo, ToolResultInfo } from '../../types/chat'
import { activeToolLabel, getToolMeta, toolOutcome, toolTarget } from './toolActivity'
import './chat-activity.css'

function duration(seconds: number) {
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export function activityCopy(activity: ChatActivity | null | undefined, calls: ToolCallInfo[], compaction?: string | null) {
  if (compaction === 'started') return { title: 'Making room to continue', detail: 'Condensing earlier conversation context for the next step.' }
  if (calls.length) return { title: calls.length > 1 ? `${calls.length} tools working in parallel` : activeToolLabel(calls[0]), detail: calls.length > 1 ? calls.map(activeToolLabel).join(' · ') : 'Waiting for this tool to return its result.' }
  if (activity?.phase === 'tool_preparing') {
    if (activity.tool_name === 'create_html_artifact' || activity.tool_name === 'revise_html_artifact') return { title: activity.tool_name === 'revise_html_artifact' ? 'Revising your page' : 'Designing your page', detail: 'Generating the HTML layout and content before the page tool runs.' }
    return { title: 'Preparing the next tool call', detail: activity.tool_name ? getToolMeta(activity.tool_name).label : 'The assistant is assembling the tool inputs.' }
  }
  if (activity?.phase === 'tool_running') return { title: getToolMeta(activity.tool_name || 'update_plan').label, detail: 'Waiting for the tool response.' }
  if (activity?.phase === 'context') return { title: 'Preparing your context', detail: activity.content || 'Loading the conversation and available sources.' }
  if (activity?.phase === 'reviewing') return { title: 'Reviewing tool results', detail: 'Using the returned information to prepare the next step.' }
  if (activity?.phase === 'writing') return { title: 'Writing your response', detail: 'The answer is appearing in the conversation.' }
  if (activity?.phase === 'model') return { title: 'Working through your request', detail: 'The assistant is preparing a response or its next tool call.' }
  return { title: 'Getting started', detail: 'Your message is sent. Waiting for the first update.' }
}

export function ChatActivityCard({ activity, calls = [], results = [], segments = [], names = {}, compactionStatus, onViewActivity }: {
  activity?: ChatActivity | null
  calls?: ToolCallInfo[]
  results?: ToolResultInfo[]
  segments?: StreamSegment[]
  names?: Record<string, string>
  compactionStatus?: string | null
  onViewActivity: () => void
}) {
  const [startedAt] = useState(Date.now)
  const [now, setNow] = useState(Date.now)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id) }, [])
  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000))
  const copy = activityCopy(activity, calls, compactionStatus)
  const callMap = new Map<string, ToolCallInfo>()
  for (const segment of segments) if (segment.kind === 'tool_call') callMap.set(segment.call.tool_call_id, segment.call)
  for (const call of calls) callMap.set(call.tool_call_id, call)
  for (const result of results) if (!callMap.has(result.tool_call_id)) callMap.set(result.tool_call_id, { ...result, args: {} })
  const resultMap = new Map(results.map(result => [result.tool_call_id, result]))
  const activeIds = new Set(calls.map(call => call.tool_call_id))
  const target = calls.length === 1 ? toolTarget(calls[0], names) : ''
  return <section className="chat-activity" aria-label="Live assistant activity">
    <div className="chat-activity-main">
      <div className="chat-activity-mark" aria-hidden="true"><Sparkles size={19} /><span /></div>
      <div className="chat-activity-copy" role="status" aria-live="polite" aria-atomic="true">
        <div className="chat-activity-eyebrow"><span className="chat-activity-dot" aria-hidden="true" />Working on your request</div>
        <div className="chat-activity-title">{copy.title}</div>
        <div className="chat-activity-detail">{target || copy.detail}</div>
      </div>
      <span className="chat-activity-time" aria-label={`Elapsed time: ${duration(elapsed)}`}><Clock3 size={12} aria-hidden="true" />{duration(elapsed)}</span>
    </div>
    <div className="chat-activity-footer">
      {callMap.size > 0 ? <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)} className="chat-activity-toggle"><ChevronDown size={13} className={expanded ? 'is-expanded' : ''} />{results.length} tool response{results.length === 1 ? '' : 's'}{calls.length > 0 ? ` · ${calls.length} active` : ''}</button> : <span className="chat-activity-note">{elapsed >= 30 && activity?.phase !== 'writing' ? 'Still working. Stop is available below.' : 'Live updates appear here as work progresses.'}</span>}
      <button type="button" className="chat-activity-jump" onClick={onViewActivity}>View activity <ArrowDown size={13} /></button>
    </div>
    {expanded && callMap.size > 0 && <ol className="chat-activity-steps" aria-label="Tool activity this turn">
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
