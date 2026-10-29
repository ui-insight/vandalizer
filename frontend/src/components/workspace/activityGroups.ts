import type { ActivityEvent } from '../../types/chat'
import { parseServerTimestamp } from '../../utils/time'

/** A chat and the extraction and workflow runs it started, newest first. */
export interface ChatGroup {
  chat: ActivityEvent
  runs: ActivityEvent[]
}

function time(iso: string | null | undefined): number {
  const t = iso ? parseServerTimestamp(iso).getTime() : 0
  return Number.isNaN(t) ? 0 : t
}

/** When anything last happened in a chat: its own last turn or its newest run. */
function lastActive(group: ChatGroup): number {
  return Math.max(
    time(group.chat.last_updated_at || group.chat.started_at),
    ...group.runs.map(r => time(r.started_at)),
  )
}

/** Split the flat activity feed into chats (each holding the runs it started)
 * and the runs started anywhere else: the editors, automations, the API.
 *
 * A run belongs to a chat by `source_conversation_id`. A run whose chat is not
 * in the feed (deleted, or older than the feed reaches) and a chat run recorded
 * before runs carried their chat go under the other runs, so nothing drops out
 * of the list.
 *
 * The chat in use comes first, whatever ran since, so its own runs can't push
 * it down the list. The other chats follow by their latest activity.
 */
export function groupActivities(
  activities: ActivityEvent[],
  currentConversationUuid: string | null | undefined,
): { chats: ChatGroup[]; otherRuns: ActivityEvent[] } {
  const byConversation = new Map<string, ChatGroup>()
  const chats: ChatGroup[] = []
  for (const a of activities) {
    if (a.type !== 'conversation') continue
    const group = { chat: a, runs: [] }
    chats.push(group)
    if (a.conversation_id) byConversation.set(a.conversation_id, group)
  }
  const otherRuns: ActivityEvent[] = []
  for (const a of activities) {
    if (a.type === 'conversation') continue
    const group = a.source_conversation_id ? byConversation.get(a.source_conversation_id) : undefined
    if (group) group.runs.push(a)
    else otherRuns.push(a)
  }
  for (const g of chats) g.runs.sort((x, y) => time(y.started_at) - time(x.started_at))
  const isCurrent = (g: ChatGroup) =>
    !!currentConversationUuid && g.chat.conversation_id === currentConversationUuid
  chats.sort((x, y) => Number(isCurrent(y)) - Number(isCurrent(x)) || lastActive(y) - lastActive(x))
  return { chats, otherRuns }
}

export function runKindLabel(activity: ActivityEvent): string {
  return activity.type === 'workflow_run' ? 'Workflow' : 'Extraction'
}

/** The template or workflow name. Chat-started workflow runs were once titled
 * "Workflow: <name>"; the kind is shown separately now. */
export function runName(activity: ActivityEvent): string {
  const title = (activity.title || '').replace(/^Workflow:\s*/, '').trim()
  return title || (activity.type === 'workflow_run' ? 'Workflow run' : 'Extraction run')
}

/** "subaward-agreement.pdf", or "subaward-agreement.pdf +2" for a batch. */
export function runDocumentLabel(activity: ActivityEvent): string {
  const titles = activity.document_titles ?? []
  if (titles.length === 0) return ''
  return titles.length > 1 ? `${titles[0]} +${titles.length - 1}` : titles[0]
}

/** "10:42" for a run today, "Oct 3" otherwise. */
export function runTimeLabel(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return ''
  const d = parseServerTimestamp(iso)
  if (Number.isNaN(d.getTime())) return ''
  const sameDay = d.toDateString() === now.toDateString()
  return sameDay
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/** The first line of an error, cut short enough to sit on one rail line. */
export function shortError(error: string, max = 80): string {
  const first = (error || '').split('\n').find(line => line.trim())?.trim() ?? ''
  return first.length > max ? `${first.slice(0, max - 1).trimEnd()}…` : first
}
