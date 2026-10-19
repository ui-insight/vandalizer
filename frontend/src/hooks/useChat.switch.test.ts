import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getHistory, streamChat } from '../api/chat'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({ getHistory: vi.fn(), streamChat: vi.fn() }))

const chatB = {
  activity_id: 'activity-b',
  messages: [
    { role: 'user' as const, content: 'What is the page limit for the Project Description?' },
    { role: 'assistant' as const, content: 'Fifteen pages.' },
  ],
  file_attachments: [], url_attachments: [],
}

/** Start Chat A's long answer and hold its stream open until finish(). */
function startChatA(result: { current: ReturnType<typeof useChat> }) {
  let onChunk!: (c: StreamChunk) => void
  let finish!: () => void
  vi.mocked(streamChat).mockImplementationOnce((...args) => new Promise(resolve => {
    onChunk = args[3]!
    finish = () => resolve({ conversationUuid: 'conversation-a', activityId: 'activity-a' })
  }))
  let sending!: Promise<void>
  act(() => { sending = result.current.send('Summarize nih-r01-neuroscience.pdf in detail.') })
  act(() => { onChunk({ kind: 'text', content: 'Aim 1: ' }) })
  return { onChunk: (c: StreamChunk) => onChunk(c), finish: () => finish(), sending }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getHistory).mockResolvedValue(chatB)
  vi.mocked(streamChat).mockResolvedValue({ conversationUuid: 'conversation-b', activityId: 'activity-b' })
})

describe('switching chats while an answer is still streaming', () => {
  it("keeps the other chat's answer out and sends the next message to the open chat", async () => {
    const { result } = renderHook(() => useChat())
    const chatA = startChatA(result)
    expect(result.current.isStreaming).toBe(true)

    await act(async () => { await result.current.loadHistory('conversation-b') })
    expect(result.current.isStreaming).toBe(false)

    await act(async () => {
      chatA.onChunk({ kind: 'text', content: 'map circuits. Key personnel: ...' })
      chatA.finish()
      await chatA.sending
    })
    expect(result.current.messages).toEqual(chatB.messages)
    expect(result.current.streamingContent).toBe('')
    expect(result.current.conversationUuid).toBe('conversation-b')
    expect(result.current.activityId).toBe('activity-b')

    await act(async () => { await result.current.send('Does that include Results from Prior NSF Support?') })
    expect(vi.mocked(streamChat).mock.calls[1][2]).toBe('activity-b')
  })

  it('a new chat started mid-stream does not inherit the old answer or its activity', async () => {
    const { result } = renderHook(() => useChat())
    const chatA = startChatA(result)

    act(() => { result.current.reset() })
    await act(async () => { chatA.finish(); await chatA.sending })
    expect(result.current.messages).toEqual([])
    expect(result.current.activityId).toBeNull()
  })

  it("reopening a chat sends follow-ups to that chat's activity, not the last one used", async () => {
    const { result } = renderHook(() => useChat())
    vi.mocked(streamChat).mockResolvedValueOnce({ conversationUuid: 'conversation-a', activityId: 'activity-a' })
    await act(async () => { await result.current.send('First question in Chat A') })
    expect(result.current.activityId).toBe('activity-a')

    await act(async () => { await result.current.loadHistory('conversation-b') })
    expect(result.current.activityId).toBe('activity-b')
  })
})
