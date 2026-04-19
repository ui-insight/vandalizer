import { useEffect, useRef, useState } from 'react'
import { ChatPanel } from '../chat/ChatPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function AssistantTab() {
  const {
    loadConversationId,
    setLoadConversationId,
    newChatSignal,
    pendingChatMessage,
    sendChatMessage,
    clearPendingChatMessage,
    verificationCompletion,
    setVerificationCompletion,
    setWorkspaceMode,
  } = useWorkspace()
  const lastLoadedRef = useRef<string | null>(null)
  const [resetKey, setResetKey] = useState(0)

  useEffect(() => {
    if (loadConversationId && loadConversationId !== lastLoadedRef.current) {
      lastLoadedRef.current = loadConversationId
      setLoadConversationId(null)
    }
  }, [loadConversationId, setLoadConversationId])

  // When newChatSignal changes, force a remount of ChatPanel to reset it
  useEffect(() => {
    if (newChatSignal > 0) {
      lastLoadedRef.current = null
      setResetKey(newChatSignal)
    }
  }, [newChatSignal])

  // When a guided verification session finishes, return the user to chat and
  // feed a follow-up message so the agent can acknowledge and (for finalized
  // sessions) naturally suggest running validation.
  useEffect(() => {
    if (!verificationCompletion) return
    const c = verificationCompletion
    setWorkspaceMode('chat')
    const msg =
      c.outcome === 'finalized'
        ? `I finished verifying extractions for "${c.documentTitle}". ${c.approvedCount} approved, ${c.correctedCount} corrected, ${c.skippedCount} skipped. Test case ${c.testCaseUuid ?? ''} has been locked in. What's next — should we run validation on this extraction set now, or add more test cases first?`
        : `I cancelled the verification session for "${c.documentTitle}" — no test case was saved.`
    sendChatMessage(msg)
    setVerificationCompletion(null)
  }, [verificationCompletion, sendChatMessage, setVerificationCompletion, setWorkspaceMode])

  return (
    <div className="h-full">
      <ChatPanel
        key={resetKey}
        conversationToLoad={lastLoadedRef.current}
        pendingMessage={pendingChatMessage}
        onPendingMessageConsumed={clearPendingChatMessage}
      />
    </div>
  )
}
