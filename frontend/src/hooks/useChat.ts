import { useState, useCallback, useRef } from 'react'
import { streamChat, getHistory, queueChatMessage } from '../api/chat'
import type { ChatMessage, Citation, ContextBudgetPlan, ContextMeterInfo, OversizeDocument, PlanTask, StreamChunk, StreamSegment, ToolCallInfo, ToolResultInfo } from '../types/chat'

export interface ContextNotice {
  action: string
  detail: string
  tokens_dropped: number
}

export interface ChatError {
  message: string
  code?: string
  suggestedAction?: 'convert_to_kb' | 'continue'
  oversizeDocuments?: OversizeDocument[]
}

const THINK_BLOCK_RE = /<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g
const THINK_TRAILING_RE = /<think(?:ing)?>[\s\S]*$/

/** Stable identity for a citation so repeated `sources` chunks don't duplicate chips. */
function citationKey(c: Citation): string {
  return (
    c.chunk_id ||
    `${c.document_id ?? ''}|${c.page ?? ''}|${c.sheet ?? ''}|${(c.content_preview ?? '').slice(0, 40)}`
  )
}

/** Map raw fetch/stream failures to a message a first-time user can act on. */
function toFriendlyError(e: unknown): string {
  if (e instanceof Error) {
    const m = e.message || ''
    if (/failed to fetch|load failed|networkerror|network error|err_|connection|stalled/i.test(m)) {
      return m && /stalled/i.test(m)
        ? m
        : 'Connection lost before the response finished. Check your network and try again.'
    }
    return m || 'Chat failed'
  }
  return 'Chat failed'
}

type SendArgs = [
  message: string,
  documentUuids?: string[],
  model?: string,
  knowledgeBaseUuid?: string,
  includeOnboardingContext?: boolean,
  folderUuids?: string[],
  isFirstSession?: boolean,
  runDemo?: boolean,
  projectUuid?: string,
]

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [thinkingContent, setThinkingContent] = useState('')
  const [thinkingDuration, setThinkingDuration] = useState<number | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationUuid, setConversationUuid] = useState<string | null>(null)
  const [activityId, setActivityId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeToolCalls, setActiveToolCalls] = useState<ToolCallInfo[]>([])
  const [toolResults, setToolResults] = useState<ToolResultInfo[]>([])
  const [segments, setSegments] = useState<StreamSegment[]>([])
  const [errorDetails, setErrorDetails] = useState<ChatError | null>(null)
  const [contextTokens, setContextTokens] = useState(0)
  const [contextMode, setContextMode] = useState<'full' | 'truncated' | 'compacted'>('full')
  const [contextCutoffIndex, setContextCutoffIndex] = useState(0)
  const [contextPlan, setContextPlan] = useState<ContextBudgetPlan | null>(null)
  const [contextNotices, setContextNotices] = useState<ContextNotice[]>([])
  // Latest backend-computed meter. Deliberately NOT cleared on send — the new
  // turn's meter arrives within the first stream chunks and replacing beats a
  // flash of "no meter" every turn.
  const [contextMeter, setContextMeter] = useState<ContextMeterInfo | null>(null)
  // Auto-compaction lifecycle for the in-flight turn ('started' while the
  // backend summarizes older messages — can take a while, so the UI shows a
  // status line instead of dead air).
  const [compactionStatus, setCompactionStatus] = useState<'started' | 'done' | 'failed' | null>(null)
  // Live checklist from update_plan (Phase 8). Survives across turns of the
  // same conversation (a follow-up "continue" resumes it); cleared on reset
  // and seeded from history on load.
  const [planTasks, setPlanTasks] = useState<PlanTask[] | null>(null)
  // Messages typed while a turn streams (Phase 10). Shown with a "Queued"
  // badge until the backend consumes them (queue_consumed chunk), at which
  // point they become regular transcript messages.
  const [queuedMessages, setQueuedMessages] = useState<string[]>([])

  const streamingRef = useRef('')
  const thinkingRef = useRef('')
  const thinkingDurationRef = useRef<number | null>(null)
  const toolCallsRef = useRef<ToolCallInfo[]>([])
  const toolResultsRef = useRef<ToolResultInfo[]>([])
  const segmentsRef = useRef<StreamSegment[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const citationsRef = useRef<Citation[]>([])
  const lastSendArgsRef = useRef<SendArgs | null>(null)

  const send = useCallback(
    async (message: string, documentUuids: string[] = [], model?: string, knowledgeBaseUuid?: string, includeOnboardingContext?: boolean, folderUuids?: string[], isFirstSession?: boolean, runDemo?: boolean, projectUuid?: string) => {
      lastSendArgsRef.current = [message, documentUuids, model, knowledgeBaseUuid, includeOnboardingContext, folderUuids, isFirstSession, runDemo, projectUuid]
      setError(null)
      setErrorDetails(null)
      setIsStreaming(true)
      setStreamingContent('')
      setThinkingContent('')
      setThinkingDuration(null)
      setActiveToolCalls([])
      setToolResults([])
      setSegments([])
      setContextPlan(null)
      setContextNotices([])
      setCompactionStatus(null)
      streamingRef.current = ''
      thinkingRef.current = ''
      thinkingDurationRef.current = null
      toolCallsRef.current = []
      toolResultsRef.current = []
      segmentsRef.current = []
      citationsRef.current = []

      // Add user message immediately
      setMessages((prev) => [...prev, { role: 'user', content: message }])

      // Build and append an assistant message from whatever has accumulated so
      // far. Shared by the normal-completion, user-stop, and network-failure
      // paths so a partial response is never silently discarded.
      const commitAssistantMessage = () => {
        const finalContent = streamingRef.current.replace(THINK_BLOCK_RE, '').trim()
        if (!finalContent && toolResultsRef.current.length === 0) return
        const assistantMsg: ChatMessage = { role: 'assistant', content: finalContent }
        if (thinkingRef.current) {
          assistantMsg.thinking = thinkingRef.current
          if (thinkingDurationRef.current != null) {
            assistantMsg.thinking_duration = thinkingDurationRef.current
          }
        }
        if (toolCallsRef.current.length > 0 || toolResultsRef.current.length > 0) {
          assistantMsg.tool_calls = [
            ...toolCallsRef.current,
            ...toolResultsRef.current.map((r) => ({
              tool_name: r.tool_name,
              tool_call_id: r.tool_call_id,
              args: {},
            })),
          ]
          assistantMsg.tool_results = [...toolResultsRef.current]
        }
        if (segmentsRef.current.length > 0) {
          assistantMsg.segments = segmentsRef.current
            .map((seg) =>
              seg.kind === 'text'
                ? { ...seg, content: seg.content.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '') }
                : seg,
            )
            .filter((seg) => seg.kind !== 'text' || seg.content.trim().length > 0)
        }
        if (citationsRef.current.length) {
          assistantMsg.citations = citationsRef.current
        }
        setMessages((prev) => [...prev, assistantMsg])
      }

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const result = await streamChat(
          message,
          documentUuids,
          activityId,
          (chunk: StreamChunk) => {
            if (chunk.kind === 'text') {
              streamingRef.current += chunk.content
              // Strip any residual think tags the backend parser missed
              const display = streamingRef.current
                .replace(THINK_BLOCK_RE, '')
                .replace(THINK_TRAILING_RE, '')
              setStreamingContent(display)

              // Build ordered segments
              const segs = segmentsRef.current
              const last = segs[segs.length - 1]
              if (last && last.kind === 'text') {
                last.content += chunk.content
              } else {
                segs.push({ kind: 'text', content: chunk.content })
              }
              setSegments([...segs])
            } else if (chunk.kind === 'thinking') {
              thinkingRef.current += chunk.content
              setThinkingContent(thinkingRef.current)
            } else if (chunk.kind === 'thinking_done') {
              thinkingDurationRef.current = chunk.duration ?? null
              setThinkingDuration(chunk.duration ?? null)
            } else if (chunk.kind === 'tool_call') {
              // update_plan renders as the pinned checklist (plan_update
              // chunk), not as a tool status line.
              if (chunk.tool_name === 'update_plan') return
              const call: ToolCallInfo = {
                tool_name: chunk.tool_name!,
                tool_call_id: chunk.tool_call_id!,
                args: chunk.args || {},
              }
              toolCallsRef.current = [...toolCallsRef.current, call]
              setActiveToolCalls([...toolCallsRef.current])
              segmentsRef.current.push({ kind: 'tool_call', call })
              setSegments([...segmentsRef.current])
            } else if (chunk.kind === 'tool_result') {
              if (chunk.tool_name === 'update_plan') return
              const res: ToolResultInfo = {
                tool_name: chunk.tool_name!,
                tool_call_id: chunk.tool_call_id!,
                content: chunk.content,
                quality: chunk.quality || null,
              }
              toolResultsRef.current = [...toolResultsRef.current, res]
              setToolResults([...toolResultsRef.current])
              // Remove from active calls
              toolCallsRef.current = toolCallsRef.current.filter(
                (c) => c.tool_call_id !== chunk.tool_call_id,
              )
              setActiveToolCalls([...toolCallsRef.current])
              segmentsRef.current.push({ kind: 'tool_result', result: res })
              setSegments([...segmentsRef.current])
            } else if (chunk.kind === 'usage') {
              setContextTokens(chunk.request_tokens ?? 0)
            } else if (chunk.kind === 'context_budget') {
              if (chunk.plan) {
                setContextPlan(chunk.plan)
                // Use the planner's estimate until the real usage chunk arrives.
                if (chunk.plan.total_input_tokens) {
                  setContextTokens(chunk.plan.total_input_tokens)
                }
              }
            } else if (chunk.kind === 'context_meter') {
              if (chunk.meter) {
                setContextMeter(chunk.meter)
              }
            } else if (chunk.kind === 'compaction') {
              setCompactionStatus(chunk.status ?? null)
            } else if (chunk.kind === 'plan_update') {
              if (chunk.plan) {
                setPlanTasks(chunk.plan)
              }
            } else if (chunk.kind === 'queue_consumed') {
              const consumed = chunk.content
              setQueuedMessages((prev) => {
                const idx = prev.indexOf(consumed)
                if (idx === -1) return prev
                const next = [...prev]
                next.splice(idx, 1)
                return next
              })
              // Promote to a regular transcript message — it now lives in
              // the turn the model is answering.
              setMessages((prev) => [...prev, { role: 'user', content: consumed }])
            } else if (chunk.kind === 'sources') {
              if (chunk.sources?.length) {
                const seen = new Set(citationsRef.current.map(citationKey))
                const merged = [...citationsRef.current]
                for (const s of chunk.sources) {
                  const k = citationKey(s)
                  if (!seen.has(k)) {
                    seen.add(k)
                    merged.push(s)
                  }
                }
                citationsRef.current = merged
              }
            } else if (chunk.kind === 'context_notice') {
              setContextNotices((prev) => [
                ...prev,
                {
                  action: chunk.action ?? 'notice',
                  detail: chunk.content,
                  tokens_dropped: chunk.tokens_dropped ?? 0,
                },
              ])
            } else if (chunk.kind === 'error') {
              setError(chunk.content)
              setErrorDetails({
                message: chunk.content,
                code: chunk.code,
                suggestedAction: chunk.suggested_action,
                oversizeDocuments: chunk.oversize_documents,
              })
            }
          },
          model,
          knowledgeBaseUuid,
          includeOnboardingContext,
          folderUuids,
          isFirstSession,
          runDemo,
          controller.signal,
          projectUuid,
        )

        setConversationUuid(result.conversationUuid)
        setActivityId(result.activityId)

        // Add assistant message from accumulated stream
        commitAssistantMessage()
      } catch (e) {
        const wasAborted =
          (e instanceof DOMException && e.name === 'AbortError') ||
          (e instanceof Error && e.name === 'AbortError')
        if (wasAborted) {
          // User hit Stop. Keep whatever partial content streamed — the backend
          // persisted it on its side; mirror that in the local message list so
          // the UI doesn't lose the response.
          commitAssistantMessage()
        } else {
          // Network drop or stalled stream. Preserve the partial response (same
          // as the Stop path) so the user doesn't lose a half-written answer,
          // then surface a recoverable, plain-language error.
          commitAssistantMessage()
          const friendly = toFriendlyError(e)
          setError(friendly)
          setErrorDetails({ message: friendly })
        }
      } finally {
        abortRef.current = null
        setIsStreaming(false)
        setStreamingContent('')
        setThinkingContent('')
        setThinkingDuration(null)
        setActiveToolCalls([])
        setToolResults([])
        setSegments([])
      }
    },
    [activityId],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const loadHistory = useCallback(async (uuid: string) => {
    try {
      const data = await getHistory(uuid)
      setMessages(data.messages)
      setConversationUuid(uuid)
      if (data.context_mode) setContextMode(data.context_mode)
      if (data.context_cutoff_index != null) setContextCutoffIndex(data.context_cutoff_index)
      setPlanTasks(data.active_plan ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load history')
    }
  }, [])

  const reset = useCallback(() => {
    setMessages([])
    setStreamingContent('')
    setThinkingContent('')
    setThinkingDuration(null)
    setIsStreaming(false)
    setConversationUuid(null)
    setActivityId(null)
    setError(null)
    setActiveToolCalls([])
    setToolResults([])
    setSegments([])
    setErrorDetails(null)
    setContextTokens(0)
    setContextMode('full')
    setContextCutoffIndex(0)
    setContextPlan(null)
    setContextNotices([])
    setContextMeter(null)
    setCompactionStatus(null)
    setPlanTasks(null)
    setQueuedMessages([])
  }, [])

  const clearError = useCallback(() => {
    setError(null)
    setErrorDetails(null)
  }, [])

  /** Re-send the last message, dropping the failed exchange so it isn't duplicated. */
  const retry = useCallback(() => {
    const args = lastSendArgsRef.current
    if (!args) return
    setMessages((prev) => {
      const next = [...prev]
      // Drop a committed partial assistant reply, then the user message —
      // send() re-appends the user message itself.
      if (next.length && next[next.length - 1].role === 'assistant') next.pop()
      if (next.length && next[next.length - 1].role === 'user') next.pop()
      return next
    })
    send(...args)
  }, [send])

  /** Queue a message typed while a turn is streaming (Phase 10). Optimistic:
   * the badge shows immediately; a failed POST rolls it back. If the stream
   * ends before the drain point, the backend folds leftovers into the next
   * turn — the badge clears when that turn's queue_consumed chunk arrives. */
  const queueMessage = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || !conversationUuid) return
    setQueuedMessages((prev) => [...prev, trimmed])
    try {
      await queueChatMessage(conversationUuid, trimmed)
    } catch (e) {
      setQueuedMessages((prev) => {
        const idx = prev.indexOf(trimmed)
        if (idx === -1) return prev
        const next = [...prev]
        next.splice(idx, 1)
        return next
      })
      setError(e instanceof Error ? e.message : 'Could not queue the message')
    }
  }, [conversationUuid])

  /** Resume a turn that stopped at the tool budget (usage_limit_resumable).
   * Unlike retry(), this keeps the partial exchange — the backend armed a
   * one-shot "resume directly, no recap" instruction for the next turn. */
  const continueRun = useCallback(() => {
    const args = lastSendArgsRef.current
    if (!args) return
    const [, ...contextArgs] = args
    setError(null)
    setErrorDetails(null)
    send('Continue', ...contextArgs)
  }, [send])

  const setActivity = useCallback((newActivityId: string, newConversationUuid: string) => {
    setActivityId(newActivityId)
    setConversationUuid(newConversationUuid)
  }, [])

  return {
    messages,
    setMessages,
    streamingContent,
    thinkingContent,
    thinkingDuration,
    isStreaming,
    conversationUuid,
    activityId,
    error,
    activeToolCalls,
    toolResults,
    segments,
    errorDetails,
    clearError,
    retry,
    continueRun,
    contextTokens,
    contextMode,
    contextCutoffIndex,
    contextPlan,
    contextNotices,
    contextMeter,
    compactionStatus,
    planTasks,
    queuedMessages,
    queueMessage,
    setContextTokens,
    setContextMode,
    setContextCutoffIndex,
    send,
    stop,
    loadHistory,
    reset,
    setActivity,
  }
}
