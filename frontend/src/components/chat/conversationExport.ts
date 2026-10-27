import type { ChatMessage } from '../../types/chat'
import { conversationEvidence } from './conversationEvidence'
import { toolResultExportText, toolResultToText } from './ToolCallDisplay'
import { THINK_BLOCK_RE, THINK_TRAILING_RE } from './markdown'
import type { ExportMessage } from '../../api/chat'

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
  const rawTexts = segs && segs.length > 0
    ? segs.flatMap((seg) => (seg.kind === 'text' && seg.content.trim() ? [seg.content.trim()] : []))
    : [message.content]
  const texts = rawTexts.map(text => message.role === 'user' ? text : text.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '').trim()).filter(Boolean)
  const toolResults = segs && segs.length > 0
    ? segs.flatMap((seg) => (seg.kind === 'tool_result' ? [seg.result] : []))
    : message.tool_results ?? []
  const tools = toolResults.map((r) => toolResultExportText(r.tool_name, r.content))
  return { texts, tools, evidence: conversationEvidence(message, names) }
}

export function exportMessages(messages: ChatMessage[], names: Record<string, string> = {}): ExportMessage[] {
  return messages.map(message => {
    const { texts, tools, evidence } = exportMessageParts(message, names)
    return { role: message.role === 'user' ? 'user' : 'assistant', content: texts.join('\n\n'), tools, evidence }
  })
}

/** Copy retains the full readable tool output, as the original message Copy did. */
export function copyMessages(messages: ChatMessage[], names: Record<string, string> = {}, includeRoles = false): string {
  return messages.map(message => {
    const parts = message.segments?.length
      ? message.segments.flatMap(segment => segment.kind === 'text' ? [segment.content] : segment.kind === 'tool_result' ? [toolResultToText(segment.result.tool_name, segment.result.content)] : [])
      : [message.content, ...(message.tool_results ?? []).map(result => toolResultToText(result.tool_name, result.content))]
    const content = parts.map(text => message.role === 'user' ? text : text.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '').trim()).filter(Boolean).join('\n\n')
    return `${includeRoles ? exportRoleLabel(message) + ':\n' : ''}${[content, conversationEvidence(message, names)].filter(Boolean).join('\n\n')}`
  }).join('\n\n---\n\n')
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
  const csvEscape = (s: string) => `"${(/^[\s]*[=+\-@]/.test(s) ? "'" + s : s).replace(/"/g, '""')}"`
  const rows = [['Role', 'Content']]
  for (const m of messages) {
    const { texts, tools, evidence } = exportMessageParts(m, names)
    rows.push([exportRoleLabel(m), [texts.join('\n'), ...tools, evidence].filter(Boolean).join('\n\n')])
  }
  return rows.map((r) => r.map(csvEscape).join(',')).join('\n')
}
