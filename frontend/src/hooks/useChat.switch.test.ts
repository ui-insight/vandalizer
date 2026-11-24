import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getHistory, streamChat } from '../api/chat'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({ getHistory: vi.fn(), streamChat: vi.fn(), queueChatMessage: vi.fn() }))

const chatB = {
  activity_id: 'activity-b',
  messages: [
    { role: 'user' as const, content: 'What is the page limit for the Project Description?' },
    { role: 'assistant' as const, content: 'Fifteen pages.' },
  ],
  file_attachments: [], url_attachments: [],
}

type Pending = { onChunk: (c: StreamChunk) => void; signal: AbortSignal; finish: () => void }

/** Start Chat A's long answer and hold its stream open until finish(). */
async function startChatA(result: { current: ReturnType<typeof useChat> }) {
  let pending!: Pending
  vi.mocked(streamChat).mockImplementationOnce((...args) => new Promise(resolve => {
    pending = {
      onChunk: args[3]!,
      signal: args[10]!,
      finish: () => resolve({ conversationUuid: 'conversation-a', activityId: 'activity-a' }),
    }
    args[12]?.({ conversationUuid: 'conversation-a', activityId: 'activity-a' })
  }))
  let sending!: Promise<void>
  act(() => { sending = result.current.send('Summarize nih-r01-neuroscience.pdf in detail.') })
  act(() => { pending.onChunk({ kind: 'text', content: 'Aim 1: ' }) })
  return { pending, sending }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getHistory).mockResolvedValue(chatB)
  vi.mocked(streamChat).mockResolvedValue({ conversationUuid: 'conversation-b', activityId: 'activity-b' })
})

describe('switching chats while an answer is still streaming', () => {
  it("keeps the other chat's answer out and sends the next message to the open chat", async () => {
    const { result } = renderHook(() => useChat())
    const { pending, sending } = await startChatA(result)
    expect(result.current.isStreaming).toBe(true)

    await act(async () => { await result.current.loadHistory('conversation-b') })
    // The server keeps writing Chat A; the client must not abort it.
    expect(pending.signal.aborted).toBe(false)
    expect(result.current.isStreaming).toBe(false)

    await act(async () => {
      pending.onChunk({ kind: 'text', content: 'map circuits. Key personnel: ...' })
      pending.finish()
      await sending
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
    const { pending, sending } = await startChatA(result)

    act(() => { result.current.reset() })
    await act(async () => { pending.finish(); await sending })
    expect(result.current.messages).toEqual([])
    expect(result.current.activityId).toBeNull()

    await act(async () => { await result.current.send('A fresh question') })
    expect(vi.mocked(streamChat).mock.calls[1][2]).toBeNull()
  })

  it('Stop in the newly opened chat does not cancel the detached answer', async () => {
    const { result } = renderHook(() => useChat())
    const { pending } = await startChatA(result)
    await act(async () => { await result.current.loadHistory('conversation-b') })
    act(() => { result.current.stop() })
    expect(pending.signal.aborted).toBe(false)
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
