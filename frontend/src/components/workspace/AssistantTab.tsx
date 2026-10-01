import { useEffect, useRef, useState } from 'react'
import { ChatPanel } from '../chat/ChatPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useTeams } from '../../hooks/useTeams'

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
    activeProjectUuid,
  } = useWorkspace()
  const { currentTeam, loading: teamsLoading, error: teamError, refreshTeams } = useTeams()
  const draftScope = `${currentTeam?.uuid ?? 'personal'}:${activeProjectUuid ?? 'home'}`
  // Keep unsent text in memory per team/project while the user browses other
  // scopes. Attachments still follow the workspace's explicit scope rules.
  const drafts = useRef(new Map<string, string>())
  const previousScope = useRef(draftScope)
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
      if (previousScope.current === draftScope) drafts.current.delete(draftScope)
      lastLoadedRef.current = null
      setResetKey(newChatSignal)
    }
    previousScope.current = draftScope
  }, [newChatSignal, draftScope])

  // When a guided verification session finishes, return the user to chat and
  // feed a follow-up message so the agent can acknowledge and (for finalized
  // sessions) naturally suggest running validation.
  useEffect(() => {
    if (!verificationCompletion) return
    const c = verificationCompletion
    setWorkspaceMode('chat')
    const msg =
      c.outcome === 'finalized'
        ? `I finished verifying extractions for "${c.documentTitle}". ${c.approvedCount} approved, ${c.correctedCount} corrected, ${c.skippedCount} skipped. Test case ${c.testCaseUuid ?? ''} has been locked in. What's next? Should we run validation on this extraction set now, or add more test cases first?`
        : `I cancelled the verification session for "${c.documentTitle}". No test case was saved.`
    sendChatMessage(msg)
    setVerificationCompletion(null)
  }, [verificationCompletion, sendChatMessage, setVerificationCompletion, setWorkspaceMode])

  // The initial team lookup establishes the draft's scope. Do not offer a
  // temporary personal composer that remounts and loses typing on arrival.
  // Existing team data stays mounted during background refreshes.
  if (!currentTeam && teamsLoading) return <p role="status" className="p-4 text-sm text-gray-600">Loading conversation workspace…</p>
  if (!currentTeam && teamError) return <div className="p-4 text-sm"><p role="alert">Could not load the conversation workspace. Your team context is unavailable.</p><button type="button" className="mt-2 rounded border px-3 py-2" onClick={() => { void refreshTeams() }}>Retry workspace</button></div>

  return (
    <div className="h-full">
      <ChatPanel
        key={`${draftScope}:${resetKey}`}
        initialDraft={drafts.current.get(draftScope) ?? ''}
        onDraftChange={draft => { if (draft) drafts.current.set(draftScope, draft); else drafts.current.delete(draftScope) }}
        conversationToLoad={lastLoadedRef.current}
        pendingMessage={pendingChatMessage}
        onPendingMessageConsumed={clearPendingChatMessage}
      />
    </div>
  )
}
