import { getProjectDefaultSkill } from '../api/projects'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { getHistory, previewSkill, selectConversationSkill, streamChat } from '../api/chat'
import { useChat } from './useChat'
import type { StreamChunk } from '../types/chat'

vi.mock('../api/projects', () => ({ getProjectDefaultSkill: vi.fn() }))
vi.mock('../api/chat', () => ({
  getHistory: vi.fn(), previewSkill: vi.fn(), selectConversationSkill: vi.fn(),
  streamChat: vi.fn(), queueChatMessage: vi.fn(), stopChatTurn: vi.fn(),
}))
const skill = { uuid: 'skill-1', title: 'Award review', version: 'v1', instructions: 'Check dates.' }
const history = { activity_id: 'a1', messages: [], url_attachments: [], file_attachments: [], active_skill: skill }

it.each([skill, null])('syncs a confirmed tool selection (%j) into the bar, transcript and follow-up', async selected => {
  const old = { ...skill, uuid: 'old', instructions: 'Old instructions.' }
  vi.mocked(getHistory).mockResolvedValueOnce({ ...history, active_skill: old })
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.loadHistory('c1') })
  vi.mocked(streamChat).mockImplementationOnce(async (_message, _docs, _activity, onChunk) => {
    onChunk?.({ kind: 'tool_result', tool_name: 'select_skill', tool_call_id: 'selection',
      content: { status: 'selected', active_skill: selected } } as unknown as StreamChunk)
    onChunk?.({ kind: 'text', content: 'Selection applied.' })
    return { activityId: 'a1', conversationUuid: 'c1' }
  })
  await act(async () => { await result.current.send('Apply Skill selection') })
  expect(result.current.activeSkill).toEqual(selected)
  expect(result.current.messages[0].active_skill).toEqual(old)
  expect(result.current.messages[1].active_skill ?? null).toEqual(selected)
  await act(async () => { await result.current.send('Continue') })
  expect(vi.mocked(streamChat).mock.calls[1].slice(13)).toEqual([selected?.uuid ?? null, selected?.version])
})

it.each([
  { needs_confirmation: true, skill_instructions: 'Proposed instructions' },
  { error: 'Access revoked' },
  { status: 'selected' },
  { status: 'selected', active_skill: { uuid: 'broken' } },
])('does not change the active Skill for an unconfirmed or incomplete result (%j)', async content => {
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.loadHistory('c1') })
  vi.mocked(streamChat).mockImplementationOnce(async (_message, _docs, _activity, onChunk) => {
    onChunk?.({ kind: 'tool_result', tool_name: 'select_skill', tool_call_id: 'selection', content } as unknown as StreamChunk)
    return { activityId: 'a1', conversationUuid: 'c1' }
  })
  await act(async () => { await result.current.send('Use a Skill') })
  expect(result.current.activeSkill).toEqual(skill)
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getProjectDefaultSkill).mockResolvedValue({ active_skill: skill })
  vi.mocked(previewSkill).mockResolvedValue(skill)
  vi.mocked(getHistory).mockResolvedValue(history)
  vi.mocked(selectConversationSkill).mockResolvedValue({ active_skill: null })
  vi.mocked(streamChat).mockResolvedValue({ activityId: 'a1', conversationUuid: 'c1' })
})

it('selects without sending a prompt and passes the reviewed version on send', async () => {
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.selectSkill('skill-1') })
  expect(result.current.activeSkill).toEqual(skill)
  expect(result.current.messages).toEqual([])
  expect(streamChat).not.toHaveBeenCalled()
  await act(async () => { await result.current.send('Review the award') })
  expect(vi.mocked(streamChat).mock.calls[0].slice(13)).toEqual(['skill-1', 'v1'])
  expect(result.current.messages[0].active_skill).toEqual(skill)
})

it('restores the pin on reopen and persists removal without a model call', async () => {
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.loadHistory('c1') })
  expect(result.current.activeSkill).toEqual(skill)
  await act(async () => { await result.current.selectSkill(null) })
  expect(selectConversationSkill).toHaveBeenCalledWith('c1', null)
  expect(result.current.activeSkill).toBeNull()
  expect(streamChat).not.toHaveBeenCalled()
  await act(async () => { await result.current.send('Continue') })
  expect(vi.mocked(streamChat).mock.calls[0][13]).toBeNull()
})

it('keeps the current Skill when switching fails', async () => {
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.loadHistory('c1') })
  vi.mocked(selectConversationSkill).mockRejectedValueOnce(new Error('Skill not found'))
  await act(async () => { await result.current.selectSkill('private-skill') })
  expect(result.current.activeSkill).toEqual(skill)
  expect(result.current.error).toBe('Skill not found')
})

it.each(['reset', 'reopen'])('discards stale selection after %s', async mode => {
  let resolve!: (value: typeof skill) => void
  vi.mocked(previewSkill).mockImplementationOnce(() => new Promise(r => { resolve = r }))
  const { result } = renderHook(() => useChat())
  let pending!: Promise<boolean>
  act(() => { pending = result.current.selectSkill('skill-1') })
  expect(result.current.isSelectingSkill).toBe(true)
  await act(async () => { await result.current.send('Too early') })
  expect(streamChat).not.toHaveBeenCalled()
  if (mode === 'reset') act(() => result.current.reset())
  else {
    vi.mocked(getHistory).mockResolvedValueOnce({ ...history, active_skill: undefined })
    await act(async () => { await result.current.loadHistory('other') })
  }
  await act(async () => { resolve(skill); await pending })
  expect(result.current.activeSkill).toBeNull()
  expect(result.current.isSelectingSkill).toBe(false)
})


it('pins a project default once per new chat and leaves existing conversations unchanged', async () => {
  const { result } = renderHook(() => useChat())
  await act(async () => { await result.current.initializeProjectSkill('p1') })
  expect(result.current.activeSkill).toEqual(skill)
  await act(async () => { await result.current.initializeProjectSkill('p1') })
  expect(getProjectDefaultSkill).toHaveBeenCalledOnce()
  await act(async () => { await result.current.loadHistory('c1') })
  await act(async () => { await result.current.initializeProjectSkill('p2') })
  expect(getProjectDefaultSkill).toHaveBeenCalledOnce()
  expect(result.current.activeSkill).toEqual(skill)
  act(() => result.current.reset())
  vi.mocked(getProjectDefaultSkill).mockResolvedValue({ active_skill: { ...skill, version: 'v2' } })
  await act(async () => { await result.current.initializeProjectSkill('p1') })
  expect(result.current.activeSkill?.version).toBe('v2')
})

it('respects explicit removal and blocks sending when a default cannot be loaded', async () => {
  const { result } = renderHook(() => useChat())
  vi.mocked(getProjectDefaultSkill).mockRejectedValueOnce(new Error('Access revoked'))
  await act(async () => { await result.current.initializeProjectSkill('p1') })
  expect(result.current.projectSkillBlocked).toBe(true)
  await act(async () => { await result.current.send('Should wait') })
  expect(streamChat).not.toHaveBeenCalled()
  await act(async () => { await result.current.selectSkill(null) })
  await act(async () => { await result.current.initializeProjectSkill('p1') })
  expect(getProjectDefaultSkill).toHaveBeenCalledOnce()
  expect(result.current.projectSkillBlocked).toBe(false)
  await act(async () => { await result.current.send('Continue without Skill') })
  expect(vi.mocked(streamChat).mock.calls[0][13]).toBeNull()
})

it('discards a late default after switching projects or opening history', async () => {
  let finish!: (value: { active_skill: typeof skill }) => void
  vi.mocked(getProjectDefaultSkill).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const { result } = renderHook(() => useChat())
  let pending!: Promise<void>
  act(() => { pending = result.current.initializeProjectSkill('p1') })
  vi.mocked(getProjectDefaultSkill).mockResolvedValueOnce({ active_skill: { ...skill, uuid: 'p2-skill' } })
  await act(async () => { await result.current.initializeProjectSkill('p2') })
  await act(async () => { finish({ active_skill: skill }); await pending })
  expect(result.current.activeSkill?.uuid).toBe('p2-skill')
  act(() => result.current.reset())
  vi.mocked(getProjectDefaultSkill).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  act(() => { pending = result.current.initializeProjectSkill('p3') })
  vi.mocked(getHistory).mockResolvedValueOnce({ ...history, active_skill: undefined })
  await act(async () => { await result.current.loadHistory('older') })
  await act(async () => { finish({ active_skill: skill }); await pending })
  expect(result.current.activeSkill).toBeNull()
})
