import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getHistory, streamChat } from '../api/chat'
import type { StreamChunk, ToolResultInfo } from '../types/chat'
import { isCertificationWriteResult } from '../lib/certificationEvents'
import { certificationPayloadIssue } from '../lib/certificationPayload'
import persistedWrites from '../components/certification/__fixtures__/chat-write-contract.json'
import { useChat } from './useChat'
vi.mock('../api/chat', () => ({ getHistory: vi.fn(), streamChat: vi.fn(), queueChatMessage: vi.fn() }))
beforeEach(() => vi.clearAllMocks())
const completed = persistedWrites.find(result => result.tool_name === 'complete_certification_module' && Number(result.content.xp_earned) > 0)!.content
const submitted = persistedWrites.find(result => result.tool_name === 'submit_certification_assessment')!.content
const provisioned = { module_id: 'foundations', provisioned_docs: [], document_names: [], folder: 'Certification Lab', message: 'No documents to provision' }
const completion: ToolResultInfo = { tool_name: 'complete_certification_module', tool_call_id: 'complete-1', quality: null, content: completed }
it('uses the real serialized persisted completion contract', () => {
  expect(completed.xp_earned).toBe(125)
  expect(certificationPayloadIssue(completion.tool_name, completion.content)).toBeNull()
})
it.each([false, true])('refreshes a live write once with incremental=%s, never on rerender or history replay', async incremental => {
  const refresh = vi.fn()
  vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
    onChunk?.({ kind: 'tool_call', ...completion, args: {}, content: '' })
    if (incremental) await Promise.resolve()
    onChunk?.({ kind: 'tool_result', ...completion } as unknown as StreamChunk)
    onChunk?.({ kind: 'tool_result', ...completion } as unknown as StreamChunk)
    return { activityId: 'a1', conversationUuid: 'c1' }
  })
  vi.mocked(getHistory).mockResolvedValue({ activity_id: 'a1', messages: [{ role: 'assistant', content: '', tool_results: [completion] }], file_attachments: [], url_attachments: [] })
  const { result, rerender, unmount } = renderHook(() => useChat({ onLiveToolResult: result => { if (isCertificationWriteResult(result)) refresh() } }))
  await act(async () => { await result.current.send('Complete my module') })
  expect(refresh).toHaveBeenCalledTimes(1)
  rerender()
  await act(async () => { await result.current.loadHistory('c1') })
  expect(refresh).toHaveBeenCalledTimes(1)
  unmount()
  const restored = renderHook(() => useChat({ onLiveToolResult: refresh }))
  await act(async () => { await restored.result.current.loadHistory('c1') })
  expect(refresh).toHaveBeenCalledTimes(1)
})
it.each([
  ['complete_certification_module', completed, true],
  ['submit_certification_assessment', submitted, true],
  ['save_certification_position', { module_id: 'm1', saved: true, position_revision: 2 }, true],
  ['save_certification_position', { module_id: 'm1', saved: true, position_revision: 2, error: 'Position changed' }, false],
  ['provision_certification_lab', provisioned, true],
  ['complete_certification_module', { module_id: 'm1', total_xp: 100 }, false],
  ['complete_certification_module', { ...completed, stars: '3' }, false],
  ['complete_certification_module', { ...completed, total_xp: -1 }, false],
  ['submit_certification_assessment', { module_id: 'm1', stored: true }, false],
  ['provision_certification_lab', { module_id: 'm1', provisioned_docs: [] }, false],
  ['save_certification_position', { module_id: 'm1', saved: true, position_revision: 0 }, false],
  ['save_certification_position', { module_id: 'm1', saved: true, position_revision: Number.NaN }, false],
  ['save_certification_position', { module_id: 'm1', saved: true, position_revision: Number.POSITIVE_INFINITY }, false],
  ['complete_certification_module', { module_id: 'm1', total_xp: 100, error: 'Failed' }, false],
  ['complete_certification_module', { module_id: 'm1', total_xp: 100, needs_confirmation: true }, false],
  ['complete_certification_module', { module_id: 'm1', total_xp: 100, status: 'cancelled' }, false],
  ['submit_certification_assessment', { module_id: 'm1', stored: false }, false],
  ['get_certification_progress', { module_id: 'm1', total_xp: 100 }, false],
  ['complete_certification_module', {}, false],
  ['complete_certification_module', null, false],
])('classifies %s %j as a successful write: %s', (tool_name, content, expected) => {
  expect(isCertificationWriteResult({ tool_name, tool_call_id: 'id', quality: null, content })).toBe(expected)
})

it('does not announce an incomplete streamed result as a completed write', async () => {
  const refresh = vi.fn()
  vi.mocked(streamChat).mockImplementation(async (_m, _d, _a, onChunk) => {
    onChunk?.({ kind: 'tool_result', ...completion, content: { module_id: 'ai_literacy', total_xp: 125 } } as unknown as StreamChunk)
    return { activityId: 'a1', conversationUuid: 'c1' }
  })
  const hook = renderHook(() => useChat({ onLiveToolResult: result => { if (isCertificationWriteResult(result)) refresh() } }))
  await act(async () => { await hook.result.current.send('Check the original result') })
  expect(refresh).not.toHaveBeenCalled()
})
