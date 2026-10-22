import type { ChatMessage } from '../../types/chat'
import { conversationEvidence } from './conversationEvidence'
import { toolResultExportText } from './ToolCallDisplay'

/** "User" or "Assistant", as the export labels a message. */
export function exportRoleLabel(message: ChatMessage): string {
  return message.role === 'user' ? 'User' : 'Assistant'
}

/**
 * One message as an export shows it: its text, one readable line per tool it
 * used, and its evidence. Exports used to print each tool's raw result as
 * JSON under its internal name (support ticket: a 3-message certification
 * chat printed as 4 pages). ``names`` maps selection IDs to titles.
 */
export function exportMessageParts(message: ChatMessage, names: Record<string, string> = {}) {
  const segs = message.segments
  const texts = segs && segs.length > 0
    ? segs.flatMap((seg) => (seg.kind === 'text' && seg.content.trim() ? [seg.content.trim()] : []))
    : [message.content]
  const toolResults = segs && segs.length > 0
    ? segs.flatMap((seg) => (seg.kind === 'tool_result' ? [seg.result] : []))
    : message.tool_results ?? []
  const tools = toolResults.map((r) => toolResultExportText(r.tool_name, r.content))
  return { texts, tools, evidence: conversationEvidence(message, names) }
}

/** The plain-text export. */
export function conversationToText(messages: ChatMessage[], names: Record<string, string> = {}): string {
  return messages.map((m) => {
    const { texts, tools, evidence } = exportMessageParts(m, names)
    return `${exportRoleLabel(m)}:\n${[...texts, ...tools, evidence].filter(Boolean).join('\n\n')}`
  }).join('\n\n---\n\n')
}

/** The CSV export: one row per message. */
export function conversationToCsv(messages: ChatMessage[], names: Record<string, string> = {}): string {
  const csvEscape = (s: string) => `"${s.replace(/"/g, '""')}"`
  const rows = [['Role', 'Content']]
  for (const m of messages) {
    const { texts, tools, evidence } = exportMessageParts(m, names)
    rows.push([exportRoleLabel(m), [texts.join('\n'), ...tools, evidence].filter(Boolean).join('\n\n')])
  }
  return rows.map((r) => r.map(csvEscape).join(',')).join('\n')
}
