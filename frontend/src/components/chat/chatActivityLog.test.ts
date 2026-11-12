import { describe, expect, it } from 'vitest'
import type { ChatActivityEntry } from '../../api/chat'
import { activityLogToText, repeatNote, whatYouDid } from './chatActivityLog'

const entry = (over: Partial<ChatActivityEntry> = {}): ChatActivityEntry => ({
  id: 'c1:2:0', call_id: 'c1', action: 'Move files', tool: 'move_documents_to_project',
  summary: 'Move 3 file(s) into project "NIFA"', time: '2026-11-09T22:00:00+00:00',
  decision: 'approved', via: 'button', outcome: 'done', detail: 'Moved 3 of 3 files.',
  approvals: 1, runs: 1, repeated: false, ...over,
})

describe('chat activity wording', () => {
  it('flags an action approved twice that ran once', () => {
    expect(repeatNote(entry({ approvals: 2, runs: 1, repeated: true }))).toBe('Approved twice, ran once.')
    expect(repeatNote(entry({ approvals: 3, runs: 0, repeated: true }))).toBe('Approved 3 times, ran never.')
    expect(repeatNote(entry())).toBeNull()
  })

  it('says how the user decided', () => {
    expect(whatYouDid(entry())).toBe('Approved Move files')
    expect(whatYouDid(entry({ via: 'typed', said: 'yes' }))).toBe('Approved Move files by replying “yes”')
    expect(whatYouDid(entry({ decision: 'cancelled', outcome: 'cancelled' }))).toBe('Cancelled Move files')
    expect(whatYouDid(entry({ decision: 'waiting', outcome: 'waiting', via: null }))).toBe('Not decided yet: Move files')
  })

  it('exports a log a support ticket can carry', () => {
    const text = activityLogToText({
      conversation_uuid: 'conv-1', title: 'NIFA subaward', waiting: 0, repeated: ['Add to inbox'],
      entries: [entry(), entry({ id: 'c5:4:1', call_id: 'c5', action: 'Add to inbox', tool: 'propose_obligations',
        outcome: 'not_run', detail: 'It was no longer waiting for approval, so nothing ran.', approvals: 2, runs: 1, repeated: true })],
    }, new Date('2026-11-10T00:00:00Z'))
    expect(text).toContain('Chat activity: NIFA subaward')
    expect(text).toContain('2026-11-09T22:00:00+00:00 · Approved Move files · ✅ Done')
    expect(text).toContain('❌ Not run')
    expect(text).toContain('Note: Approved twice, ran once.')
    expect(text).toContain('Card: c5 (propose_obligations)')
  })
})
