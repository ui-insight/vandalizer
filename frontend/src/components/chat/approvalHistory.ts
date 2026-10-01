import type { ChatMessage, ToolCallInfo, ToolResultInfo } from '../../types/chat'

export type ApprovalRecord = { label: string; detail: string }

function calls(message: ChatMessage): ToolCallInfo[] {
  return [...new Map([...(message.tool_calls ?? []), ...(message.segments?.flatMap(s => s.kind === 'tool_call' ? [s.call] : []) ?? [])].map(call => [call.tool_call_id, call])).values()]
}
function results(message: ChatMessage): ToolResultInfo[] {
  return [...new Map([...(message.tool_results ?? []), ...(message.segments?.flatMap(s => s.kind === 'tool_result' ? [s.result] : []) ?? [])].map(result => [result.tool_call_id, result])).values()]
}
function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`
  return JSON.stringify(value) ?? 'undefined'
}
function actionKey(call: ToolCallInfo): string {
  const args = Object.fromEntries(Object.entries(call.args).filter(([key]) => key !== 'confirmed'))
  return `${call.tool_name}:${canonical(args)}`
}

/** Only associate an execution with a preview when the next turn contains the
 * same tool and exact arguments (apart from its confirmation flag). A later
 * unrelated run must never make an old approval look completed. */
export function approvalHistoryFor(message: ChatMessage, following: ChatMessage[]): Record<string, ApprovalRecord> {
  if (!following.length) return {}
  const previews = results(message).filter(result => object(result.content).needs_confirmation === true)
  const output: Record<string, ApprovalRecord> = {}
  for (const preview of previews) {
    const original = calls(message).find(call => call.tool_call_id === preview.tool_call_id)
    let record: ApprovalRecord = { label: 'Earlier action preview', detail: 'This preview is no longer actionable. See the later messages for the decision and outcome.' }
    const nextUser = following.findIndex(m => m.role === 'user')
    if (nextUser >= 0) {
      const decision = following[nextUser].content.trim()
      if (decision === 'Yes, go ahead') record = { label: 'Approval requested', detail: 'You sent approval. Execution is not confirmed by this preview.' }
      if (decision === 'No, cancel that') record = { label: 'Cancellation requested', detail: 'You asked the Assistant to cancel this action. This preview cannot be approved again.' }
      const nextTurn = following.slice(nextUser + 1)
      const end = nextTurn.findIndex(m => m.role === 'user')
      for (const response of end < 0 ? nextTurn : nextTurn.slice(0, end)) {
        const execution = original && calls(response).find(call => call.args.confirmed === true && actionKey(call) === actionKey(original))
        const result = execution && results(response).find(r => r.tool_call_id === execution.tool_call_id)
        if (!result) continue
        const content = object(result.content)
        if (content.needs_confirmation) continue
        const status = content.status
        const label = status === 'canceled' || status === 'cancelled' ? 'Canceled'
          : content.error || status === 'failed' || status === 'error' ? 'Failed'
          : status === 'queued' || status === 'pending' ? 'Queued'
          : status === 'running' ? 'Running'
          : status === 'completed' ? 'Completed'
          : result.tool_name === 'create_workflow' && content.workflow_id ? 'Workflow created'
          : result.tool_name === 'run_workflow' && content.session_id ? 'Run accepted'
          : 'Result recorded'
        record = { label, detail: 'A matching confirmed action has a result below. Inspect that result for details; this preview is retained as history.' }
        break
      }
    }
    output[preview.tool_call_id] = record
  }
  return output
}
