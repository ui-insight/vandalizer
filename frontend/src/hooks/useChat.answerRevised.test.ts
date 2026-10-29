import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChat } from './useChat'
import { streamChat } from '../api/chat'
vi.mock('../api/chat', () => ({ streamChat: vi.fn(), getHistory: vi.fn(), queueChatMessage: vi.fn(), stopChatTurn: vi.fn() }))

// A KB answer the server checked against its passages and rewrote replaces
// what streamed, as the server stores it (chat_answer_repair).
beforeEach(() => vi.clearAllMocks())

describe('a revised answer', () => {
  it('replaces the streamed text and keeps the tool segments and the check', async () => {
    const check = { version: 1, outcome: 'repaired', original_answer: 'Requests must be sent 10 days ahead.' }
    vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
      onChunk?.({ kind: 'text', content: 'Let me search. ' })
      onChunk?.({ kind: 'tool_call', tool_name: 'search_knowledge_base', tool_call_id: 't1', args: {}, content: '' })
      onChunk?.({ kind: 'text', content: 'Requests must be sent 10 days ahead.' })
      onChunk?.({ kind: 'answer_revised', content: 'Requests should be sent 10 days ahead.', answer_check: check })
      return { conversationUuid: 'c', activityId: 'a' }
    })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('When are extension requests due?') })

    const msg = result.current.messages.at(-1)
    expect(msg?.content).toBe('Requests should be sent 10 days ahead.')
    expect(msg?.segments?.map(s => s.kind)).toEqual(['tool_call', 'text'])
    expect(msg?.segments?.at(-1)).toEqual({ kind: 'text', content: 'Requests should be sent 10 days ahead.' })
    expect(msg?.answer_check).toEqual(check)
  })

  it('leaves an answer that was not revised as it streamed', async () => {
    vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
      onChunk?.({ kind: 'text', content: 'Requests should be sent 10 days ahead.' })
      return { conversationUuid: 'c', activityId: 'a' }
    })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('When are extension requests due?') })

    expect(result.current.messages.at(-1)?.content).toBe('Requests should be sent 10 days ahead.')
    expect(result.current.messages.at(-1)?.answer_check).toBeUndefined()
  })
})
