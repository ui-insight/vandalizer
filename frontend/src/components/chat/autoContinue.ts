/**
 * Decide whether attaching content to the chat should automatically continue
 * the conversation (by queueing a brief acknowledgement) instead of leaving the
 * assistant idle after it asked the user to upload something.
 *
 * Kept as a pure predicate so the guard logic is unit-testable in isolation from
 * ChatPanel's state.
 */
export function shouldAutoContinueAfterAttach(args: {
  /** Role of the most recent message in the conversation, if any. */
  lastMessageRole: string | undefined
  /** True while the assistant is producing a response. */
  isStreaming: boolean
  /** True when the user already queued a message (theirs takes precedence). */
  hasHeldMessage: boolean
}): boolean {
  const { lastMessageRole, isStreaming, hasHeldMessage } = args
  // Only nudge when the assistant spoke last (it's waiting on the user), the
  // chat is idle, and nothing is already queued. A fresh chat with no messages
  // has no assistant prompt to continue, so it's skipped.
  return lastMessageRole === 'assistant' && !isStreaming && !hasHeldMessage
}
