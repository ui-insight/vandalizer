import { useState, useCallback, useRef } from 'react'
import { streamChat, getHistory } from '../api/chat'
import type { ChatMessage, ContextBudgetPlan, StreamChunk } from '../types/chat'

export interface ContextNotice {
  action: string
  detail: string
  tokens_dropped: number
}

const THINK_BLOCK_RE = /<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g
const THINK_TRAILING_RE = /<think(?:ing)?>[\s\S]*$/

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [thinkingContent, setThinkingContent] = useState('')
  const [thinkingDuration, setThinkingDuration] = useState<number | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationUuid, setConversationUuid] = useState<string | null>(null)
  const [activityId, setActivityId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [contextTokens, setContextTokens] = useState(0)
  const [contextMode, setContextMode] = useState<'full' | 'truncated' | 'compacted'>('full')
  const [contextCutoffIndex, setContextCutoffIndex] = useState(0)
  const [contextPlan, setContextPlan] = useState<ContextBudgetPlan | null>(null)
  const [contextNotices, setContextNotices] = useState<ContextNotice[]>([])

  const streamingRef = useRef('')
  const thinkingRef = useRef('')
  const thinkingDurationRef = useRef<number | null>(null)

  const send = useCallback(
    async (message: string, documentUuids: string[] = [], model?: string, knowledgeBaseUuid?: string, includeOnboardingContext?: boolean, folderUuids?: string[], isFirstSession?: boolean) => {
      setError(null)
      setIsStreaming(true)
      setStreamingContent('')
      setThinkingContent('')
      setThinkingDuration(null)
      setContextPlan(null)
      setContextNotices([])
      streamingRef.current = ''
      thinkingRef.current = ''
      thinkingDurationRef.current = null

      // Add user message immediately
      setMessages((prev) => [...prev, { role: 'user', content: message }])

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
            } else if (chunk.kind === 'thinking') {
              thinkingRef.current += chunk.content
              setThinkingContent(thinkingRef.current)
            } else if (chunk.kind === 'thinking_done') {
              thinkingDurationRef.current = chunk.duration ?? null
              setThinkingDuration(chunk.duration ?? null)
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
            }
          },
          model,
          knowledgeBaseUuid,
          includeOnboardingContext,
          folderUuids,
          isFirstSession,
        )

        setConversationUuid(result.conversationUuid)
        setActivityId(result.activityId)

        // Add assistant message from accumulated stream
        const finalContent = streamingRef.current.replace(THINK_BLOCK_RE, '').trim()
        if (finalContent) {
          const assistantMsg: ChatMessage = {
            role: 'assistant',
            content: finalContent,
          }
          if (thinkingRef.current) {
            assistantMsg.thinking = thinkingRef.current
            if (thinkingDurationRef.current != null) {
              assistantMsg.thinking_duration = thinkingDurationRef.current
            }
          }
          setMessages((prev) => [...prev, assistantMsg])
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Chat failed')
      } finally {
        setIsStreaming(false)
        setStreamingContent('')
        setThinkingContent('')
        setThinkingDuration(null)
      }
    },
    [activityId],
  )

  const loadHistory = useCallback(async (uuid: string) => {
    try {
      const data = await getHistory(uuid)
      setMessages(data.messages)
      setConversationUuid(uuid)
      if (data.context_mode) setContextMode(data.context_mode)
      if (data.context_cutoff_index != null) setContextCutoffIndex(data.context_cutoff_index)
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
    setContextTokens(0)
    setContextMode('full')
    setContextCutoffIndex(0)
    setContextPlan(null)
    setContextNotices([])
  }, [])

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
    contextTokens,
    contextMode,
    contextCutoffIndex,
    contextPlan,
    contextNotices,
    setContextTokens,
    setContextMode,
    setContextCutoffIndex,
    send,
    loadHistory,
    reset,
    setActivity,
  }
}
