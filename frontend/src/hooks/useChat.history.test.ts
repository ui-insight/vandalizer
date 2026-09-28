import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getHistory, streamChat } from '../api/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({ getHistory: vi.fn(), streamChat: vi.fn(), queueChatMessage: vi.fn() }))
const saved = {
  activity_id: 'activity-original',
  messages: [
    { role: 'user' as const, content: 'Build a recurring review workflow.' },
    { role: 'assistant' as const, content: 'We agreed on extraction, review, then a summary.' },
  ],
  file_attachments: [], url_attachments: [],
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getHistory).mockResolvedValue(saved)
  vi.mocked(streamChat).mockResolvedValue({ activityId: 'activity-original', conversationUuid: 'conversation-original' })
})

describe('resuming a saved conversation', () => {
  it('restores the transcript without a model call and sends the follow-up to the same activity', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.loadHistory('conversation-original') })
    expect(result.current.messages).toEqual(saved.messages)
    expect(result.current.activityId).toBe('activity-original')
    expect(streamChat).not.toHaveBeenCalled()
    await act(async () => { await result.current.send('Add an approval step after review.') })
    expect(vi.mocked(streamChat).mock.calls[0].slice(0, 3)).toEqual(['Add an approval step after review.', [], 'activity-original'])
    expect(result.current.messages.slice(0, 2)).toEqual(saved.messages)
  })

  it('waits for history and ignores stale results when another conversation is selected', async () => {
    let resolveFirst!: (value: typeof saved) => void
    vi.mocked(getHistory).mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
    const { result } = renderHook(() => useChat())
    let first!: Promise<void>
    act(() => { first = result.current.loadHistory('first') })
    expect(result.current.isLoadingHistory).toBe(true)
    await act(async () => { await result.current.send('Too early') })
    expect(streamChat).not.toHaveBeenCalled()
    await act(async () => { await result.current.loadHistory('second') })
    await act(async () => { resolveFirst({ ...saved, activity_id: 'stale' }); await first })
    expect(result.current.conversationUuid).toBe('second')
    expect(result.current.activityId).toBe('activity-original')
    expect(result.current.isLoadingHistory).toBe(false)
  })

  it.each(['unavailable', 'missing activity'])('does not silently create a fresh chat if history is %s', async mode => {
    if (mode === 'unavailable') vi.mocked(getHistory).mockRejectedValueOnce(new Error('History unavailable'))
    else vi.mocked(getHistory).mockResolvedValueOnce({ ...saved, activity_id: null })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.loadHistory('conversation-original') })
    await act(async () => { await result.current.send('Continue') })
    expect(streamChat).not.toHaveBeenCalled()
    expect(result.current.error).toMatch(/could not be resumed/)
  })
})
