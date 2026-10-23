import { describe, expect, it } from 'vitest'
import {
  groupActivities, runDocumentLabel, runName, runTimeLabel, shortError,
} from './activityGroups'
import type { ActivityEvent } from '../../types/chat'

function ev(overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: 'x', type: 'search_set_run', status: 'completed', title: 'NSF Subaward Extraction',
    conversation_id: null, search_set_uuid: 'ss-1', workflow_id: null, workflow_session_id: null,
    started_at: '2026-10-15T10:00:00Z', finished_at: null, last_updated_at: null,
    error: '', tokens_input: 0, tokens_output: 0, message_count: 0, result_snapshot: {},
    meta_summary: {}, ...overrides,
  }
}

const chatA = ev({ id: 'chat-a', type: 'conversation', conversation_id: 'conv-a', title: 'Full Life Cycle Test',
  started_at: '2026-10-15T09:00:00Z', last_updated_at: '2026-10-15T09:30:00Z' })
const chatB = ev({ id: 'chat-b', type: 'conversation', conversation_id: 'conv-b', title: 'Older chat',
  started_at: '2026-10-15T08:00:00Z', last_updated_at: '2026-10-15T08:10:00Z' })

describe('groupActivities (ticket: which chat produced each run)', () => {
  it('puts each run under the chat that started it, newest first', () => {
    const r1 = ev({ id: 'r1', source_conversation_id: 'conv-a', started_at: '2026-10-15T10:42:00Z' })
    const r2 = ev({ id: 'r2', type: 'workflow_run', source_conversation_id: 'conv-a', started_at: '2026-10-15T11:05:00Z' })
    const { chats, otherRuns } = groupActivities([r2, r1, chatA, chatB], null)

    expect(chats.map(g => g.chat.id)).toEqual(['chat-a', 'chat-b'])
    expect(chats[0].runs.map(r => r.id)).toEqual(['r2', 'r1'])
    expect(chats[1].runs).toEqual([])
    expect(otherRuns).toEqual([])
  })

  it('keeps the chat in use on top, however recently others ran', () => {
    const recent = ev({ id: 'r', source_conversation_id: 'conv-a', started_at: '2026-10-15T12:00:00Z' })
    const { chats } = groupActivities([recent, chatA, chatB], 'conv-b')
    expect(chats.map(g => g.chat.id)).toEqual(['chat-b', 'chat-a'])
  })

  it("orders other chats by their newest run, not when the chat began", () => {
    const run = ev({ id: 'r', source_conversation_id: 'conv-b', started_at: '2026-10-15T13:00:00Z' })
    const { chats } = groupActivities([run, chatA, chatB], null)
    expect(chats.map(g => g.chat.id)).toEqual(['chat-b', 'chat-a'])
  })

  it('lists editor runs, legacy chat runs and runs of a missing chat as other runs', () => {
    const editor = ev({ id: 'editor' })
    const legacy = ev({ id: 'legacy' })
    const orphan = ev({ id: 'orphan', source_conversation_id: 'conv-deleted' })
    const { chats, otherRuns } = groupActivities([editor, legacy, orphan, chatA], null)
    expect(chats[0].runs).toEqual([])
    expect(otherRuns.map(r => r.id)).toEqual(['editor', 'legacy', 'orphan'])
  })
})

describe('run labels', () => {
  it('drops the old "Workflow:" prefix from chat-started workflow titles', () => {
    expect(runName(ev({ type: 'workflow_run', title: 'Workflow: Subaward Review Summary v2' })))
      .toBe('Subaward Review Summary v2')
    expect(runName(ev({ title: null }))).toBe('Extraction run')
  })

  it('names the first document and counts the rest', () => {
    expect(runDocumentLabel(ev({ document_titles: ['subaward-agreement.pdf'] }))).toBe('subaward-agreement.pdf')
    expect(runDocumentLabel(ev({ document_titles: ['a.pdf', 'b.pdf', 'c.pdf'] }))).toBe('a.pdf +2')
    expect(runDocumentLabel(ev({}))).toBe('')
  })

  it('shows a time for today and a date otherwise', () => {
    const now = new Date('2026-10-15T15:00:00')
    expect(runTimeLabel('2026-10-15T10:42:00', now)).toMatch(/10:42/)
    expect(runTimeLabel('2026-10-03T10:42:00', now)).toMatch(/Oct/)
    expect(runTimeLabel(null, now)).toBe('')
  })

  it('cuts an error to its first line', () => {
    expect(shortError('failed: name already exists\nTraceback ...')).toBe('failed: name already exists')
    const long = 'x'.repeat(200)
    expect(shortError(long)).toHaveLength(80)
    expect(shortError(long).endsWith('…')).toBe(true)
  })
})
