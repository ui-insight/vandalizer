import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getHistory, queueChatMessage, streamChat, stopChatTurn } from '../api/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({ streamChat: vi.fn(), getHistory: vi.fn(), queueChatMessage: vi.fn(), stopChatTurn: vi.fn() }))
const identity = { conversationUuid: 'budget-chat', activityId: 'budget-activity' }
const request = 'Add a one-line summary at the top of the NIH R01 Budget Dashboard page.'

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(stopChatTurn).mockResolvedValue({ success: true })
  vi.mocked(streamChat).mockImplementation(async (...args) => {
    args[3]?.({ kind: 'text', content: `Answered: ${args[0]}` })
    return identity
  })
})

function holdReply(announceIdentity = true) {
  let finish!: () => void
  let fail!: () => void
  vi.mocked(streamChat).mockImplementationOnce((...args) => {
    if (announceIdentity) args[12]?.(identity)
    args[3]?.({ kind: 'text', content: 'Version saved.' })
    return new Promise((resolve, reject) => {
      finish = () => resolve(identity)
      fail = () => reject(new TypeError('Failed to fetch'))
      args[10]?.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError')))
    })
  })
  return { finish: () => finish(), fail: () => fail() }
}

it.each([false, true])('delivers a busy-chat request once as its own turn (identity announced: %s)', async announceIdentity => {
  const held = holdReply(announceIdentity)
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('save this new version', ['workbook'], 'kimi-k3', ['kb'], undefined, ['folder'], undefined, true, 'project', undefined, 'old-approval') })
  await act(async () => { await result.current.queueMessage(request) })
  expect(streamChat).toHaveBeenCalledTimes(1)
  expect(result.current.queuedMessages).toEqual([request])
  expect(queueChatMessage).not.toHaveBeenCalled()
  await act(async () => { held.finish() })
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2))
  const next = vi.mocked(streamChat).mock.calls[1]
  expect(next[0]).toBe(request)
  expect(next[1]).toEqual(['workbook'])
  expect(next[2]).toBe('budget-activity')
  expect(next[4]).toBe('kimi-k3')
  expect(next[5]).toEqual(['kb'])
  expect(next[7]).toEqual(['folder'])
  expect(next[9]).toBeUndefined() // Never run the previous demo again.
  expect(next[11]).toBe('project')
  expect(next[15]).toBe(false) // A new request, not a retry of the approval.
  expect(next[16]).toBeUndefined()
  expect(result.current.queuedMessages).toEqual([])
  expect(result.current.messages.map(message => [message.role, message.content])).toEqual([
    ['user', 'save this new version'], ['assistant', 'Version saved.'],
    ['user', request], ['assistant', `Answered: ${request}`],
  ])
})

it('preserves FIFO order and intentionally repeated requests', async () => {
  const held = holdReply()
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Start') })
  await act(async () => {
    await result.current.queueMessage(request, ['current-doc'], 'current-model')
    await result.current.queueMessage('Next')
    await result.current.queueMessage('Next')
  })
  await act(async () => { held.finish() })
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(4))
  expect(vi.mocked(streamChat).mock.calls.map(call => call[0])).toEqual(['Start', request, 'Next', 'Next'])
  expect(vi.mocked(streamChat).mock.calls[1][1]).toEqual(['current-doc'])
  expect(vi.mocked(streamChat).mock.calls[1][4]).toBe('current-model')
})

it('queues a direct send racing with the streaming UI state instead of discarding it', async () => {
  const held = holdReply()
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Start') })
  await act(async () => { await result.current.send(request) })
  expect(streamChat).toHaveBeenCalledTimes(1)
  await act(async () => { held.finish() })
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2))
  expect(vi.mocked(streamChat).mock.calls[1][0]).toBe(request)
})

it.each(['stop', 'connection'])('holds unsent requests after %s until explicitly resumed', async reason => {
  const held = holdReply()
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Start') })
  await act(async () => { await result.current.queueMessage(request) })
  await act(async () => { if (reason === 'stop') result.current.stop(); else held.fail() })
  await waitFor(() => expect(result.current.isStreaming).toBe(false))
  expect(streamChat).toHaveBeenCalledTimes(1)
  expect(result.current.queuedMessages).toEqual([request])
  act(() => result.current.resumeQueuedMessages())
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2))
  expect(vi.mocked(streamChat).mock.calls[1][0]).toBe(request)
})

it('does not send a queued page edit into a different conversation', async () => {
  const held = holdReply()
  vi.mocked(getHistory).mockResolvedValue({ activity_id: 'different-activity', messages: [], file_attachments: [], url_attachments: [] })
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Start') })
  await act(async () => { await result.current.queueMessage(request) })
  await act(async () => { await result.current.loadHistory('different-chat'); held.finish() })
  expect(streamChat).toHaveBeenCalledTimes(1)
  expect(result.current.queuedMessages).toEqual([])
  expect(result.current.messages).toEqual([])
})
