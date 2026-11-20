import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import type { ChatMessage, ToolCallInfo, ToolResultInfo } from '../../types/chat'

type ToolReference = Pick<ToolCallInfo, 'tool_name'>

/** Known course entry requests or real course tools, not arbitrary assistant prose. */
export function hasCertificationContext(messages: ChatMessage[], currentTools: ToolReference[] = []): boolean {
  const latestUser = messages.filter(message => message.role === 'user').at(-1)
  if (/^(?:start|continue|resume)(?:\s+(?:my|the|vandalizer))*\s+certification\b/i.test(latestUser?.content.trim() ?? '')) return true
  const tools = [...currentTools, ...messages.flatMap(message => [
    ...(message.tool_calls ?? []), ...(message.tool_results ?? []),
    ...(message.segments ?? []).flatMap<ToolReference>(segment => segment.kind === 'tool_call' ? [segment.call]
      : segment.kind === 'tool_result' ? [segment.result] : []),
  ])]
  return tools.some(tool => /^(?:get|check|complete|submit|provision|save)_certification_/.test(tool.tool_name))
}

/** Render only inside a failed chat response; this recovery reads course state. */
export function CertificationChatRecovery({ messages, toolCalls = [], toolResults = [] }: {
  messages: ChatMessage[]; toolCalls?: ToolCallInfo[]; toolResults?: ToolResultInfo[]
}) {
  const certification = useCertificationPanelOptional()
  if (!certification || !hasCertificationContext(messages, [...toolCalls, ...toolResults])) return null
  return <div className="mt-3 border-t border-red-200 pt-3">
    <p>Open your course to read lessons and check saved work before retrying an uncertain action.</p>
    <button type="button" className="mt-2 min-h-11 rounded-md border border-red-700 bg-white px-3 py-2 font-medium text-red-900 focus-visible:outline-2 focus-visible:outline-offset-2" onClick={() => {
      certification.openPanel()
      if (!certification.loading) void certification.refresh()
    }}>Open course without chat</button>
  </div>
}
