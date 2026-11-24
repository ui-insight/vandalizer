import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { postBrowserResult, streamChat } from '../api/chat'
import { isBrowserExtensionReady, runBrowserTool } from '../lib/browserExtension'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({
  streamChat: vi.fn(),
  postBrowserResult: vi.fn(() => Promise.resolve({ status: 'ok' })),
  stopChatTurn: vi.fn(() => Promise.resolve()),
}))
vi.mock('../lib/browserExtension', () => ({
  BROWSER_TOOL_NAMES: new Set(['browser_open', 'browser_read', 'browser_click']),
  detectBrowserExtension: vi.fn(() => Promise.resolve(true)),
  isBrowserExtensionReady: vi.fn(() => true),
  runBrowserTool: vi.fn(),
}))

beforeEach(() => { vi.clearAllMocks() })

it('runs browser calls in the extension in order, posts each result, and tells the server the extension is there', async () => {
  let emit!: (chunk: StreamChunk) => void
  let finish!: () => void
  vi.mocked(streamChat).mockImplementation((_m, _d, _a, onChunk) => new Promise(resolve => {
    emit = onChunk!; finish = () => resolve({ conversationUuid: 'c', activityId: 'a' })
  }))
  const order: string[] = []
  let releaseOpen!: () => void
  vi.mocked(runBrowserTool).mockImplementation((tool) => {
    order.push(`start ${tool}`)
    if (tool === 'browser_open') return new Promise(resolve => { releaseOpen = () => { order.push('end browser_open'); resolve({ page: { text: 'opened' } }) } })
    order.push(`end ${tool}`)
    return Promise.resolve({ page: { text: 'read' } })
  })

  const { result } = renderHook(() => useChat())
  let sending!: Promise<void>
  act(() => { sending = result.current.send('Check the balance') })
  expect(vi.mocked(streamChat).mock.calls[0].at(-1)).toBe(true)
  expect(isBrowserExtensionReady).toHaveBeenCalled()
  act(() => vi.mocked(streamChat).mock.calls[0][12]?.({ conversationUuid: 'c', activityId: 'a' }))

  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_open', tool_call_id: 'open-1', args: { url: 'https://fin.example.edu' }, relay: true }))
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_read', tool_call_id: 'read-1', args: { query: 'balance' }, relay: true, browser_allowed_hosts: ['example.edu'] }))
  // Not marked by the server (withheld tool or bad arguments): never runs.
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_read', tool_call_id: 'read-unrelayed', args: {} }))
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'web_search', tool_call_id: 'web-1', args: {} }))
  await waitFor(() => expect(order).toEqual(['start browser_open']))
  await act(async () => { releaseOpen() })
  await waitFor(() => expect(postBrowserResult).toHaveBeenCalledTimes(2))
  // The second call waits for the first: one tab, driven in order.
  expect(order).toEqual(['start browser_open', 'end browser_open', 'start browser_read', 'end browser_read'])
  expect(vi.mocked(postBrowserResult).mock.calls).toEqual([
    ['open-1', { page: { text: 'opened' } }],
    ['read-1', { page: { text: 'read' } }],
  ])
  expect(runBrowserTool).toHaveBeenCalledWith('browser_open', { url: 'https://fin.example.edu' }, undefined, 'c')
  // The administrator's site list travels with the call for the extension to enforce.
  expect(runBrowserTool).toHaveBeenCalledWith('browser_read', { query: 'balance' }, ['example.edu'], 'c')
  await act(async () => { finish(); await sending })
})

it('drops browser calls still queued when the person presses Stop', async () => {
  let emit!: (chunk: StreamChunk) => void
  vi.mocked(streamChat).mockImplementation((_m, _d, _a, onChunk, ...rest) => new Promise((_resolve, reject) => {
    emit = onChunk!
    const signal = rest.find((arg): arg is AbortSignal => arg instanceof AbortSignal)
    signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  let releaseOpen!: () => void
  vi.mocked(runBrowserTool).mockImplementation((tool) => tool === 'browser_open'
    ? new Promise(resolve => { releaseOpen = () => resolve({ page: { text: 'opened' } }) })
    : Promise.resolve({ ok: true }))

  const { result } = renderHook(() => useChat())
  act(() => { void result.current.send('Check the balance') })
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_open', tool_call_id: 'open-1', args: { url: 'https://fin.example.edu' }, relay: true }))
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_click', tool_call_id: 'click-1', args: { ref: 3 }, relay: true }))
  await waitFor(() => expect(runBrowserTool).toHaveBeenCalledTimes(1))

  act(() => { result.current.stop() })
  await act(async () => { releaseOpen() })
  await new Promise(resolve => setTimeout(resolve, 20))
  expect(runBrowserTool).toHaveBeenCalledTimes(1)
  expect(runBrowserTool).not.toHaveBeenCalledWith('browser_click', expect.anything())
})
