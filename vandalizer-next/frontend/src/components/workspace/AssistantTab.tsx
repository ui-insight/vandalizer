import { useEffect, useRef, useState } from 'react'
import { ChatPanel } from '../chat/ChatPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'

export function AssistantTab() {
  const {
    loadConversationId,
    setLoadConversationId,
    newChatSignal,
    pendingChatMessage,
    clearPendingChatMessage,
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
