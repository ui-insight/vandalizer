import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'
import { streamChat } from '../api/chat'
vi.mock('../api/chat', () => ({ streamChat: vi.fn(), getHistory: vi.fn(), queueChatMessage: vi.fn() }))
beforeEach(() => vi.clearAllMocks())
describe('interrupted agent responses', () => {
  it('retains a tool call even when stopped before text or a result arrives', async () => {
    vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk, _model, _kb, _o, _f, _first, _demo, signal) => {
      onChunk?.({ kind: 'tool_call', tool_name: 'create_workflow', tool_call_id: 'pending', args: { name: 'Review' }, content: '' })
      return new Promise((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError'))))
    })
    const { result } = renderHook(() => useChat())
    let pending!: Promise<void>
    act(() => { pending = result.current.send('Create review') })
    await act(async () => { result.current.stop(); await pending })
    expect(result.current.messages.at(-1)).toMatchObject({ role: 'assistant', interruption: 'stopped', tool_calls: [{ tool_call_id: 'pending' }] })
    expect(result.current.isStreaming).toBe(false)
  })
  it('preserves successful siblings and the unresolved call after a network failure', async () => {
    vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
      onChunk?.({ kind: 'tool_call', tool_name: 'create_workflow', tool_call_id: 'done', args: {}, content: '' })
      onChunk?.({ kind: 'tool_result', tool_name: 'create_workflow', tool_call_id: 'done', content: { workflow_id: 'wf-1' } } as unknown as StreamChunk)
      onChunk?.({ kind: 'tool_call', tool_name: 'run_workflow', tool_call_id: 'pending', args: {}, content: '' })
      throw new TypeError('Failed to fetch')
    })
    const { result } = renderHook(() => useChat())
    await act(async () => { await result.current.send('Create then run') })
    expect(result.current.messages.at(-1)).toMatchObject({ interruption: 'connection', tool_results: [{ tool_call_id: 'done', content: { workflow_id: 'wf-1' } }] })
    expect(result.current.messages.at(-1)?.tool_calls?.some(call => call.tool_call_id === 'pending')).toBe(true)
    expect(result.current.error).toBeTruthy()
    vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
      onChunk?.({ kind: 'text', content: 'Checking the existing workflow.' })
      return { conversationUuid: 'review-conversation', activityId: 'review-activity' }
    })
    act(() => result.current.retry())
    await waitFor(() => expect(result.current.isStreaming).toBe(false))
    expect(result.current.messages).toHaveLength(4)
    expect(result.current.messages[1].tool_results?.[0].content).toEqual({ workflow_id: 'wf-1' })
    expect(result.current.messages.at(-1)?.content).toBe('Checking the existing workflow.')
  })
})
