import { describe, it, expect } from 'vitest'
import { inFlightText, settleReprocesses } from './kbSourceReprocess'
import type { KnowledgeBaseSource, SourceCurrency } from '../../types/knowledge'

function src(uuid: string, overrides: Partial<KnowledgeBaseSource> = {}): KnowledgeBaseSource {
  return { uuid, source_type: 'document', status: 'ready', chunk_count: 12, created_at: '2026-09-01T00:00:00Z', ...overrides }
}

const currency = (c: Partial<SourceCurrency>) => c as SourceCurrency

describe('settleReprocesses', () => {
  it('keeps running sources and reports finished ones with their chunk count or error', () => {
    const tracked = {
      a: { mode: 'reindex' as const, name: 'A' },
      b: { mode: 'reextract' as const, name: 'B' },
      c: { mode: 'reindex' as const, name: 'C' },
      gone: { mode: 'reindex' as const, name: 'Removed' },
    }
    const { remaining, settled } = settleReprocesses(tracked, [
      src('a', { chunk_count: 42 }),
      src('b', { status: 'error', error_message: 'OCR service returned 500.' }),
      src('c', { status: 'processing' }),
    ])

    expect(Object.keys(remaining)).toEqual(['c'])
    expect(settled).toEqual([
      { uuid: 'a', name: 'A', ok: true, chunkCount: 42, error: null, keptPrevious: false, unchanged: false },
      { uuid: 'b', name: 'B', ok: false, chunkCount: 12, error: 'OCR service returned 500', keptPrevious: false, unchanged: false },
    ])
  })

  it('reads a failed re-fetch from the currency outcome, since the source stays ready', () => {
    const { settled } = settleReprocesses(
      { u: { mode: 'refetch', name: 'Page' } },
      [src('u', {
        source_type: 'url',
        currency: currency({ last_refresh_outcome: 'retrieval_failed', last_refresh_error: 'HTTP 403' }),
      })],
    )
    expect(settled[0]).toMatchObject({ ok: false, keptPrevious: true, error: 'HTTP 403' })
  })

  it('says when a re-fetched page was unchanged', () => {
    const { settled } = settleReprocesses(
      { u: { mode: 'refetch', name: 'Page' } },
      [src('u', { source_type: 'url', currency: currency({ last_refresh_outcome: 'unchanged' }) })],
    )
    expect(settled[0]).toMatchObject({ ok: true, unchanged: true })
  })
})

describe('inFlightText', () => {
  it('names the stage a reprocess is in', () => {
    expect(inFlightText('pending', 'reextract')).toMatch(/re-reading the document/)
    expect(inFlightText('pending', 'reindex')).toMatch(/queued/)
    expect(inFlightText('processing', 'reindex')).toMatch(/Indexing/)
    // Without a reprocess in this session, a pending document source is
    // waiting on its extraction, as before.
    expect(inFlightText('pending')).toMatch(/Waiting for document text/)
  })
})
