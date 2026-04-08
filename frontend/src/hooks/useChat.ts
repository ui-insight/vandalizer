import { useState, useCallback, useRef } from 'react'
import { streamChat, getHistory } from '../api/chat'
import type { ChatMessage, StreamChunk, ToolCallInfo, ToolResultInfo } from '../types/chat'

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
  const [activeToolCalls, setActiveToolCalls] = useState<ToolCallInfo[]>([])
  const [toolResults, setToolResults] = useState<ToolResultInfo[]>([])

  const streamingRef = useRef('')
  const thinkingRef = useRef('')
  const thinkingDurationRef = useRef<number | null>(null)
  const toolCallsRef = useRef<ToolCallInfo[]>([])
  const toolResultsRef = useRef<ToolResultInfo[]>([])

  const send = useCallback(
    async (message: string, documentUuids: string[] = [], model?: string, knowledgeBaseUuid?: string, includeOnboardingContext?: boolean, folderUuids?: string[], isFirstSession?: boolean) => {
      setError(null)
      setIsStreaming(true)
      setStreamingContent('')
      setThinkingContent('')
      setThinkingDuration(null)
      setActiveToolCalls([])
      setToolResults([])
      streamingRef.current = ''
      thinkingRef.current = ''
      thinkingDurationRef.current = null
      toolCallsRef.current = []
      toolResultsRef.current = []

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
            } else if (chunk.kind === 'tool_call') {
              const call: ToolCallInfo = {
                tool_name: chunk.tool_name!,
                tool_call_id: chunk.tool_call_id!,
                args: chunk.args || {},
              }
              toolCallsRef.current = [...toolCallsRef.current, call]
              setActiveToolCalls([...toolCallsRef.current])
            } else if (chunk.kind === 'tool_result') {
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
        if (finalContent || toolResultsRef.current.length > 0) {
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
          if (toolCallsRef.current.length > 0 || toolResultsRef.current.length > 0) {
            assistantMsg.tool_calls = [...toolCallsRef.current, ...toolResultsRef.current.map((r) => ({
              tool_name: r.tool_name,
              tool_call_id: r.tool_call_id,
              args: {},
            }))]
            assistantMsg.tool_results = [...toolResultsRef.current]
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
        setActiveToolCalls([])
        setToolResults([])
      }
    },
    [activityId],
  )

  const loadHistory = useCallback(async (uuid: string) => {
    try {
      const data = await getHistory(uuid)
      setMessages(data.messages)
      setConversationUuid(uuid)
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
    activeToolCalls,
    toolResults,
    send,
    loadHistory,
    reset,
    setActivity,
  }
}
