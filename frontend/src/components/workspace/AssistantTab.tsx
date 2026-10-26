import { useEffect, useRef, useState } from 'react'
import { ChatPanel } from '../chat/ChatPanel'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useTeams } from '../../hooks/useTeams'

/** Map-like per-scope store backed by sessionStorage; falls back to memory. */
function sessionStore(prefix: string) {
  const memory = new Map<string, string>()
  return {
    get(scope: string): string | undefined {
      try { return sessionStorage.getItem(prefix + scope) ?? undefined } catch { return memory.get(scope) }
    },
    set(scope: string, value: string) {
      try { sessionStorage.setItem(prefix + scope, value) } catch { memory.set(scope, value) }
    },
    delete(scope: string) {
      try { sessionStorage.removeItem(prefix + scope) } catch { memory.delete(scope) }
    },
  }
}

const sessionDrafts = sessionStore('vandalizer:chat-draft:')
// The conversation open in each scope. Web links and uploads attached before
// sending live on that conversation, so reopening it on return restores them
// along with the draft (#1014 item 50).
const sessionConversations = sessionStore('vandalizer:chat-conversation:')

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
    currentConversationUuid,
  } = useWorkspace()
  const { currentTeam, loading: teamsLoading, error: teamError, refreshTeams } = useTeams()
  const draftScope = `${currentTeam?.uuid ?? 'personal'}:${activeProjectUuid ?? 'home'}`
  // Keep unsent text per team/project while the user browses other scopes,
  // other pages and the Library. Session storage outlives this component, so
  // opening a source, alert or project doesn't discard a half-written
  // question. Attachments still follow the workspace's explicit scope rules.
  const drafts = useRef(sessionDrafts)
  const previousScope = useRef(draftScope)
  const lastLoadedRef = useRef<string | null>(null)
  const [resetKey, setResetKey] = useState(0)

  // Remember the scope's conversation when the panel's conversation changes,
  // not when the scope does: right after a scope switch the context still
  // holds the previous scope's conversation until the old panel unmounts.
  const lastConversationRef = useRef(currentConversationUuid)
  useEffect(() => {
    if (currentConversationUuid === lastConversationRef.current) return
    lastConversationRef.current = currentConversationUuid
    if (currentConversationUuid) sessionConversations.set(draftScope, currentConversationUuid)
  }, [currentConversationUuid, draftScope])

  useEffect(() => {
    if (loadConversationId && loadConversationId !== lastLoadedRef.current) {
      lastLoadedRef.current = loadConversationId
      setLoadConversationId(null)
    }
  }, [loadConversationId, setLoadConversationId])

  // When newChatSignal changes, force a remount of ChatPanel to reset it.
  // Compare with the signal seen at mount: the signal stays above zero after
  // any earlier New Chat or scope switch, and remounting the Assistant (after
  // leaving the workspace) is not a new chat — it must not wipe the draft.
  const lastSignalRef = useRef(newChatSignal)
  useEffect(() => {
    if (newChatSignal !== lastSignalRef.current) {
      lastSignalRef.current = newChatSignal
      if (previousScope.current === draftScope) {
        drafts.current.delete(draftScope)
        sessionConversations.delete(draftScope)
      }
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
        workspaceLabel={currentTeam ? `Team: ${currentTeam.name}` : 'Personal workspace'}
        initialDraft={drafts.current.get(draftScope) ?? ''}
        onDraftChange={draft => { if (draft) drafts.current.set(draftScope, draft); else drafts.current.delete(draftScope) }}
        conversationToLoad={lastLoadedRef.current ?? sessionConversations.get(draftScope) ?? null}
        pendingMessage={pendingChatMessage}
        onPendingMessageConsumed={clearPendingChatMessage}
      />
    </div>
  )
}
