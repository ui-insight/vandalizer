import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getHistory, queueChatMessage, streamChat, stopChatTurn } from '../api/chat'
import { useChat } from './useChat'
import type { StreamChunk } from '../types/chat'
import { approvalHistoryFor } from '../components/chat/approvalHistory'

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

// Tool results carry JSON objects on the wire; StreamChunk still types content as text.
type WireChunk = Omit<StreamChunk, 'content'> & { content: unknown }

function holdReply(announceIdentity = true, chunks: WireChunk[] = [{ kind: 'text', content: 'Version saved.' }]) {
  let finish!: () => void
  let fail!: () => void
  vi.mocked(streamChat).mockImplementationOnce((...args) => {
    if (announceIdentity) args[12]?.(identity)
    chunks.forEach(chunk => args[3]?.(chunk as StreamChunk))
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

const previewId = 'footer-preview'
const previewChunks: WireChunk[] = [
  { kind: 'tool_call', content: '', tool_name: 'revise_html_artifact', tool_call_id: 'footer', args: { title: 'Budget' } },
  { kind: 'tool_result', tool_name: 'revise_html_artifact', tool_call_id: 'footer', content: {
    preview_id: previewId, needs_confirmation: true, artifact_preview_html: '<footer>Prepared for grant admins</footer>',
  } },
  { kind: 'text', content: 'Click Save new version to save it.' },
]
const savedChunks: WireChunk[] = [
  { kind: 'tool_result', tool_name: 'revise_html_artifact', tool_call_id: 'save-footer', content: {
    preview_id: previewId, artifact_uuid: 'budget-page', revision: 'revision-with-footer', version: 2,
  } },
]

it.each(['save', 'cancel'])('keeps the first Page card actionable until %s, then sends the queued edit', async decision => {
  const preview = holdReply(true, previewChunks)
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Add a footer: Prepared for grant admins') })
  await act(async () => { await result.current.queueMessage(request) })
  await act(async () => { preview.finish() })
  expect(result.current.awaitingPageApproval).toBe(true)
  expect(streamChat).toHaveBeenCalledTimes(1)
  expect(result.current.messages).toHaveLength(2)
  expect(approvalHistoryFor(result.current.messages[1], [], false)).toEqual({})
  act(() => result.current.resumeQueuedMessages())
  expect(streamChat).toHaveBeenCalledTimes(1)

  const approval = holdReply(true, decision === 'save' ? savedChunks : [{ kind: 'text', content: 'Cancelled.' }])
  act(() => { void result.current.send(decision === 'save' ? 'Yes, go ahead' : 'No, cancel that', [], undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, decision === 'save' ? previewId : undefined) })
  expect(streamChat).toHaveBeenCalledTimes(2)
  expect(result.current.queuedMessages).toEqual([request])
  await act(async () => { approval.finish() })
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(3))
  expect(vi.mocked(streamChat).mock.calls[2][0]).toBe(request)
  expect(result.current.awaitingPageApproval).toBe(false)
})

it.each(['failed', 'unconfirmed'])('holds queued edits after an %s save until a retry confirms it', async outcome => {
  const preview = holdReply(true, previewChunks)
  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Add footer') })
  await act(async () => { preview.finish() })
  // A new request also queues when the preview has already finished.
  await act(async () => { await result.current.send(request) })
  expect(streamChat).toHaveBeenCalledTimes(1)
  const save = holdReply(true, outcome === 'failed'
    ? [{ kind: 'tool_result', tool_name: 'revise_html_artifact', tool_call_id: 'save-footer', content: { preview_id: previewId, error: 'Save failed' } }]
    : [{ kind: 'text', content: 'Saved your page.' }])
  act(() => { void result.current.send('Yes, go ahead', [], undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, previewId) })
  await act(async () => { if (outcome === 'failed') save.fail(); else save.finish() })
  expect(result.current.awaitingPageApproval).toBe(true)
  act(() => result.current.resumeQueuedMessages())
  expect(streamChat).toHaveBeenCalledTimes(2)
  const retry = holdReply(true, savedChunks)
  act(() => { void result.current.retry() })
  await act(async () => { retry.finish() })
  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(4))
  expect(vi.mocked(streamChat).mock.calls[2][16]).toBe(previewId)
  expect(vi.mocked(streamChat).mock.calls[3][0]).toBe(request)
})
