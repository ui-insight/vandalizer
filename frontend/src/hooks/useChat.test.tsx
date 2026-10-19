import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const mockStreamChat = vi.fn()
const mockGetHistory = vi.fn()

vi.mock('../api/chat', () => ({
  streamChat: (...args: unknown[]) => mockStreamChat(...args),
  getHistory: (...args: unknown[]) => mockGetHistory(...args),
}))

import { useChat } from './useChat'

const history = {
  messages: [
    { role: 'user', content: 'What is the budget?' },
    { role: 'assistant', content: '$10,000.' },
  ],
  url_attachments: [],
  file_attachments: [],
  activity_id: 'act-1',
  scope: {
    documents: [{ uuid: 'd-1', title: 'Proposal.pdf' }],
    folders: [],
    knowledge_bases: [{ uuid: 'kb-1', title: 'Policies' }],
    unavailable: 0,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetHistory.mockResolvedValue(history)
  mockStreamChat.mockResolvedValue({ conversationUuid: 'conv-1', activityId: 'act-1' })
})

describe('useChat reopening a conversation', () => {
  it('continues the reopened conversation instead of starting a new one', async () => {
    // Support ticket: a follow-up after reopening from the Activity rail went
    // out with no activity id, so the server started a fresh conversation
    // without the earlier turns.
    const { result } = renderHook(() => useChat())

    await act(async () => { await result.current.loadHistory('conv-1') })
    expect(result.current.activityId).toBe('act-1')

    await act(async () => { await result.current.send('And year 2?', ['d-1']) })
    expect(mockStreamChat.mock.calls[0][2]).toBe('act-1')
  })

  it('hands the history back so the caller can restore its attachments', async () => {
    const { result } = renderHook(() => useChat())
    let loaded: unknown
    await act(async () => { loaded = await result.current.loadHistory('conv-1') })
    expect(loaded).toEqual(history)
  })

  it('resolves to null when the history cannot be loaded', async () => {
    mockGetHistory.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useChat())
    let loaded: unknown = 'unset'
    await act(async () => { loaded = await result.current.loadHistory('conv-1') })
    expect(loaded).toBeNull()
    expect(result.current.error).toBe('boom')
  })
})
