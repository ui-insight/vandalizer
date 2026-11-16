import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { postBrowserResult, streamChat } from '../api/chat'
import { isBrowserExtensionReady, runBrowserTool } from '../lib/browserExtension'
import type { StreamChunk } from '../types/chat'
import { useChat } from './useChat'

vi.mock('../api/chat', () => ({ streamChat: vi.fn(), postBrowserResult: vi.fn(() => Promise.resolve({ status: 'ok' })) }))
vi.mock('../lib/browserExtension', () => ({
  BROWSER_TOOL_NAMES: new Set(['browser_open', 'browser_read']),
  detectBrowserExtension: vi.fn(() => Promise.resolve(true)),
  isBrowserExtensionReady: vi.fn(() => true),
  runBrowserTool: vi.fn(),
}))

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

  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_open', tool_call_id: 'open-1', args: { url: 'https://fin.example.edu' } }))
  act(() => emit({ kind: 'tool_call', content: '', tool_name: 'browser_read', tool_call_id: 'read-1', args: { query: 'balance' } }))
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
  expect(runBrowserTool).toHaveBeenCalledWith('browser_open', { url: 'https://fin.example.edu' })
  await act(async () => { finish(); await sending })
})
