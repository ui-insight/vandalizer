import { describe, it, expect } from 'vitest'
import { sortKBs } from './KBGridView'
import type { KnowledgeBase } from '../../types/knowledge'

function kb(overrides: Partial<KnowledgeBase>): KnowledgeBase {
  return {
    uuid: 'kb-x',
    title: 'KB',
    description: '',
    status: 'ready',
    shared_with_team: false,
    team_owned: false,
    verified: false,
    organization_ids: [],
    tags: [],
    team_id: null,
    total_sources: 0,
    sources_ready: 0,
    sources_failed: 0,
    total_chunks: 0,
    created_at: '2026-01-01T00:00:00+00:00',
    updated_at: '2026-01-01T00:00:00+00:00',
    ...overrides,
  }
}

describe('sortKBs — Recently Used', () => {
  it('orders by last_used_at descending', () => {
    const older = kb({ uuid: 'older', last_used_at: '2026-07-01T00:00:00+00:00' })
    const newer = kb({ uuid: 'newer', last_used_at: '2026-07-20T00:00:00+00:00' })
    const sorted = sortKBs([older, newer], 'recent')
    expect(sorted.map(k => k.uuid)).toEqual(['newer', 'older'])
  })

  it('puts never-used KBs after used ones, preserving their fetched order', () => {
    const neverA = kb({ uuid: 'never-a' })
    const neverB = kb({ uuid: 'never-b', last_used_at: null })
    const used = kb({ uuid: 'used', last_used_at: '2026-07-20T00:00:00+00:00' })
    const sorted = sortKBs([neverA, neverB, used], 'recent')
    expect(sorted.map(k => k.uuid)).toEqual(['used', 'never-a', 'never-b'])
  })

  it('does not mutate the input array', () => {
    const input = [
      kb({ uuid: 'a', last_used_at: '2026-07-01T00:00:00+00:00' }),
      kb({ uuid: 'b', last_used_at: '2026-07-20T00:00:00+00:00' }),
    ]
    sortKBs(input, 'recent')
    expect(input.map(k => k.uuid)).toEqual(['a', 'b'])
  })
})
