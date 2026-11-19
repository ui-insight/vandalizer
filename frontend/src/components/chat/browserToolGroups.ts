import type { StreamSegment, ToolCallInfo, ToolResultInfo } from '../../types/chat'

export const isBrowserTool = (name: string) => name.startsWith('browser_') || name === 'record_value'
export type BrowserGroup = { kind: 'browser_group'; calls: ToolCallInfo[] }

/** A browser call that did nothing yet: it is waiting for the person to approve the site.
 * ``still_waiting`` is the same site asked for again while its card waits. */
export function browserAwaitingApproval(result?: ToolResultInfo): boolean {
  const content = result?.content
  if (!content || typeof content !== 'object') return false
  const value = content as Record<string, unknown>
  return value.needs_confirmation === true || value.still_waiting === true
}

/** Keep narrated text and other tools in order while combining adjacent browser work.
 *
 * A browser call waiting for approval stays out of the group: it renders as an
 * ordinary approval card, the only place with the "Open site" button (support
 * ticket: chat said "Click Open site on the card above" and the browser card
 * had no such button and logged the step as completed). */
export function groupBrowserSegments(segments: StreamSegment[], results?: ReadonlyMap<string, ToolResultInfo>): (StreamSegment | BrowserGroup)[] {
  const grouped: (StreamSegment | BrowserGroup)[] = []
  let current: BrowserGroup | undefined
  for (const segment of segments) {
    if (segment.kind === 'tool_result' && isBrowserTool(segment.result.tool_name)) continue
    if (segment.kind === 'tool_call' && isBrowserTool(segment.call.tool_name) && !browserAwaitingApproval(results?.get(segment.call.tool_call_id))) {
      if (!current) { current = { kind: 'browser_group', calls: [] }; grouped.push(current) }
      current.calls.push(segment.call)
    } else {
      if (segment.kind === 'text' && !segment.content.trim()) continue
      current = undefined
      grouped.push(segment)
    }
  }
  return grouped
}
