import { useState, useCallback, useRef } from 'react'
import { streamChat, getHistory } from '../api/chat'
import type { ChatMessage, StreamChunk } from '../types/chat'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [thinkingContent, setThinkingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationUuid, setConversationUuid] = useState<string | null>(null)
  const [activityId, setActivityId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const streamingRef = useRef('')
  const thinkingRef = useRef('')

  const send = useCallback(
    async (message: string, documentUuids: string[] = [], model?: string) => {
      setError(null)
      setIsStreaming(true)
      setStreamingContent('')
      setThinkingContent('')
      streamingRef.current = ''
      thinkingRef.current = ''

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
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: streamingRef.current },
          ])
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Chat failed')
      } finally {
        setIsStreaming(false)
        setStreamingContent('')
        setThinkingContent('')
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
    setIsStreaming(false)
    setConversationUuid(null)
    setActivityId(null)
    setError(null)
  }, [])

  return {
    messages,
    streamingContent,
    thinkingContent,
    isStreaming,
    conversationUuid,
    activityId,
    error,
    send,
    loadHistory,
    reset,
  }
}
