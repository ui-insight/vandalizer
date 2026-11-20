import type { ChatActivityEntry, ChatActivityLog } from '../../api/chat'

/** Support ticket (NIFA subaward setup test): in a long chat the user couldn't
 * tell what they approved, how many times, or whether it ran. These helpers
 * word the Activity timeline and its exported copy the same way. */

export const OUTCOME_TEXT: Record<ChatActivityEntry['outcome'], { icon: string; text: string }> = {
  done: { icon: '✅', text: 'Done' },
  partial: { icon: '⚠️', text: 'Partly done' },
  not_run: { icon: '❌', text: 'Not run' },
  cancelled: { icon: '⛔', text: 'Cancelled' },
  waiting: { icon: '⏳', text: 'Waiting for you' },
  no_result: { icon: '…', text: 'Still working' },
}

function times(n: number): string {
  return n === 1 ? 'once' : n === 2 ? 'twice' : `${n} times`
}

/** "Approved twice, ran once." — shown on every row of an action approved more than once. */
export function repeatNote(entry: ChatActivityEntry): string | null {
  if (!entry.repeated) return null
  return `Approved ${times(entry.approvals)}, ran ${entry.runs === 0 ? 'never' : times(entry.runs)}.`
}

/** What you did, in plain words. */
export function whatYouDid(entry: ChatActivityEntry): string {
  if (entry.decision === 'waiting') return `Not decided yet: ${entry.action}`
  if (entry.decision === 'cancelled') return `Cancelled ${entry.action}`
  return entry.via === 'typed'
    ? `Approved ${entry.action} by replying “${entry.said ?? 'yes'}”`
    : `Approved ${entry.action}`
}

export function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** Plain-text log to attach to a support ticket. */
export function activityLogToText(log: ChatActivityLog, now = new Date()): string {
  const lines = [
    `Chat activity: ${log.title || 'Untitled chat'}`,
    `Conversation: ${log.conversation_uuid}`,
    `Exported: ${now.toISOString()}`,
    '',
  ]
  if (!log.entries.length) lines.push('No approvals in this chat.')
  for (const e of log.entries) {
    const o = OUTCOME_TEXT[e.outcome]
    lines.push(`${e.time ?? 'unknown time'} · ${whatYouDid(e)} · ${o.icon} ${o.text}`)
    if (e.summary) lines.push(`    Action: ${e.summary}`)
    if (e.detail) lines.push(`    Result: ${e.detail}`)
    const note = repeatNote(e)
    if (note) lines.push(`    Note: ${note}`)
    lines.push(`    Card: ${e.call_id} (${e.tool})`)
  }
  return lines.join('\n') + '\n'
}
