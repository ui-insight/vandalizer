import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { streamChat } from '../api/chat'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'
vi.mock('../api/chat', () => ({ streamChat: vi.fn() }))

it('keeps preparation separate from tool execution, ignores heartbeats, and clears activity on completion', async () => {
  let emit!: (chunk: StreamChunk) => void
  let finish!: () => void
  vi.mocked(streamChat).mockImplementation((_m, _d, _a, onChunk) => new Promise(resolve => {
    emit = onChunk!; finish = () => resolve({ conversationUuid: 'c', activityId: 'a' })
  }))
  const { result } = renderHook(() => useChat())
  let sending!: Promise<void>
  act(() => { sending = result.current.send('Create a page') })
  expect(result.current.activity?.phase).toBe('starting')
  act(() => emit({ kind: 'activity', content: '', activity: { phase: 'tool_preparing', tool_name: 'create_html_artifact' } }))
  expect(result.current.activity?.phase).toBe('tool_preparing')
  expect(result.current.activeToolCalls).toEqual([])
  act(() => emit({ kind: 'heartbeat', content: '' }))
  expect(result.current.activity?.phase).toBe('tool_preparing')
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'create_html_artifact', tool_call_id: 'page', args: {} }))
  expect(result.current.activity?.phase).toBe('tool_running')
  act(() => emit({ kind: 'tool_result', content: '', tool_name: 'create_html_artifact', tool_call_id: 'page' }))
  expect(result.current.activity?.phase).toBe('reviewing')
  expect(result.current.activity?.tool_name).toBe('create_html_artifact')
  expect(result.current.activity?.tool_call_id).toBe('page')
  act(() => emit({ kind: 'text', content: 'Preview ready.' }))
  expect(result.current.activity?.phase).toBe('writing')
  await act(async () => { finish(); await sending })
  expect(result.current.activity).toBeNull()
  expect(result.current.messages.at(-1)?.content).toBe('Preview ready.')
  expect(JSON.stringify(result.current.messages)).not.toContain('tool_preparing')
})
