import type { ChatMessage, ToolCallInfo, ToolResultInfo } from '../types/chat'

const pageTools = new Set(['create_html_artifact', 'revise_html_artifact'])
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' ? value as Record<string, unknown> : {}

export function pageDecision(message: string): 'approve' | 'cancel' | null {
  const text = message.trim().replace(/[.!]$/, '').toLowerCase()
  if (['yes', 'yes, go ahead', 'save', 'save page', 'save new version'].includes(text)) return 'approve'
  if (['no', 'no, cancel that', 'cancel', 'cancel action', 'cancel page'].includes(text)) return 'cancel'
  return null
}

/** A queued request must not make an unsaved Page preview historical. */
export function hasPendingPageApproval(messages: ChatMessage[]): boolean {
  const pending = new Map<string, { tool: string; stored: boolean }>()
  for (const message of messages) {
    if (message.role === 'user') {
      const decision = pageDecision(message.content)
      if (decision === 'cancel') {
        // The card's cancellation refers to the most recent proposal.
        const latest = [...pending.keys()].at(-1)
        if (latest) pending.delete(latest)
      } else if (!decision) {
        // Older transcripts may have continued past a preview. Only hold the
        // current decision boundary; send() now queues new requests before
        // they can cross it. Approval/retry turns retain unresolved proposals.
        pending.clear()
      }
      continue
    }
    const calls = new Map<string, ToolCallInfo>()
    for (const call of [...(message.tool_calls ?? []), ...(message.segments?.flatMap(s => s.kind === 'tool_call' ? [s.call] : []) ?? [])]) calls.set(call.tool_call_id, call)
    const results = new Map<string, ToolResultInfo>()
    for (const result of [...(message.tool_results ?? []), ...(message.segments?.flatMap(s => s.kind === 'tool_result' ? [s.result] : []) ?? [])]) results.set(result.tool_call_id, result)
    for (const result of results.values()) {
      if (!pageTools.has(result.tool_name)) continue
      const content = object(result.content)
      const id = typeof content.preview_id === 'string' ? content.preview_id : calls.get(result.tool_call_id)?.args.preview_id
      if (content.needs_confirmation === true && !content.error) {
        pending.set(typeof id === 'string' ? id : result.tool_call_id, { tool: result.tool_name, stored: typeof id === 'string' })
      } else if (!content.error && typeof content.artifact_uuid === 'string' && content.artifact_uuid
        && typeof content.revision === 'string' && content.revision) {
        if (typeof id === 'string') pending.delete(id)
        else {
          // Compatibility for old cards without stored preview IDs. Never use
          // an unassociated receipt to resolve a modern immutable preview.
          const legacy = [...pending].filter(([, entry]) => !entry.stored && entry.tool === result.tool_name)
          if (legacy.length === 1) pending.delete(legacy[0][0])
        }
      }
    }
  }
  return pending.size > 0
}
