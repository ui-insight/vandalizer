import { useState, useCallback, useRef } from 'react'
import { streamChat, getHistory } from '../api/chat'
import type { ChatMessage, StreamChunk } from '../types/chat'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [thinkingContent, setThinkingContent] = useState('')
  const [thinkingDuration, setThinkingDuration] = useState<number | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationUuid, setConversationUuid] = useState<string | null>(null)
  const [activityId, setActivityId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const streamingRef = useRef('')
  const thinkingRef = useRef('')
  const thinkingDurationRef = useRef<number | null>(null)

  const send = useCallback(
    async (message: string, documentUuids: string[] = [], model?: string) => {
      setError(null)
      setIsStreaming(true)
      setStreamingContent('')
      setThinkingContent('')
      setThinkingDuration(null)
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
          null,
          (chunk: StreamChunk) => {
            if (chunk.kind === 'text') {
              streamingRef.current += chunk.content
              setStreamingContent(streamingRef.current)
            } else if (chunk.kind === 'thinking') {
              thinkingRef.current += chunk.content
              setThinkingContent(thinkingRef.current)
            } else if (chunk.kind === 'thinking_done') {
              thinkingDurationRef.current = chunk.duration ?? null
              setThinkingDuration(chunk.duration ?? null)
            } else if (chunk.kind === 'error') {
              setError(chunk.content)
            }
          },
          model,
        )

        setConversationUuid(result.conversationUuid)
        setActivityId(result.activityId)

        // Add assistant message from accumulated stream
        if (streamingRef.current) {
          const assistantMsg: ChatMessage = {
            role: 'assistant',
            content: streamingRef.current,
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
  }, [])

  return {
    messages,
    streamingContent,
    thinkingContent,
    thinkingDuration,
    isStreaming,
    conversationUuid,
    activityId,
    error,
    send,
    loadHistory,
    reset,
  }
}
