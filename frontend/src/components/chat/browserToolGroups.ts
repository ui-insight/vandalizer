import type { StreamSegment, ToolCallInfo } from '../../types/chat'

export const isBrowserTool = (name: string) => name.startsWith('browser_') || name === 'record_value'
export type BrowserGroup = { kind: 'browser_group'; calls: ToolCallInfo[] }

/** Keep narrated text and other tools in order while combining adjacent browser work. */
export function groupBrowserSegments(segments: StreamSegment[]): (StreamSegment | BrowserGroup)[] {
  const grouped: (StreamSegment | BrowserGroup)[] = []
  let current: BrowserGroup | undefined
  for (const segment of segments) {
    if (segment.kind === 'tool_result' && isBrowserTool(segment.result.tool_name)) continue
    if (segment.kind === 'tool_call' && isBrowserTool(segment.call.tool_name)) {
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
