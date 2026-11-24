import type { ChatActivity } from '../types/chat'

/** Page HTML can stream for a while before a complete tool call/card exists. */
export function isPagePreparation(activity: ChatActivity | null | undefined): boolean {
  return activity?.phase === 'tool_preparing'
    && (activity.tool_name === 'create_html_artifact' || activity.tool_name === 'revise_html_artifact')
}
