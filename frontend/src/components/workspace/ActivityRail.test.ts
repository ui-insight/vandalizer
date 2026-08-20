import { describe, expect, it } from 'vitest'
import { activeReviewUuid, isStale, pendingReviewUuid } from './ActivityRail'
import type { ActivityEvent } from '../../types/chat'

function run(overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: 'a1',
    type: 'workflow_run',
    status: 'running',
    title: 'Subaward review',
    conversation_id: null,
    search_set_uuid: null,
    workflow_id: 'wf-1',
    workflow_session_id: 's-1',
    started_at: '2026-08-18T00:00:00Z',
    finished_at: null,
    // Two hours of silence — well past any sane threshold.
    last_updated_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    error: '',
    tokens_input: 0,
    tokens_output: 0,
    message_count: 0,
    result_snapshot: {},
    meta_summary: {},
    ...overrides,
  }
}

describe('pendingReviewUuid', () => {
  it('reads the marker a paused run carries', () => {
    expect(pendingReviewUuid(run({ meta_summary: { pending_review_uuid: 'appr-9' } })))
      .toBe('appr-9')
  })

  it('is null on an ordinary run', () => {
    expect(pendingReviewUuid(run())).toBeNull()
  })

  it('is null when meta_summary is absent', () => {
    expect(pendingReviewUuid(run({ meta_summary: undefined }))).toBeNull()
  })

  it('rejects a non-string marker rather than rendering it', () => {
    // A malformed value must not produce a link to /reviews/[object Object].
    expect(pendingReviewUuid(run({ meta_summary: { pending_review_uuid: { a: 1 } } })))
      .toBeNull()
  })

  it('treats an empty string as no marker', () => {
    expect(pendingReviewUuid(run({ meta_summary: { pending_review_uuid: '' } })))
      .toBeNull()
  })
})

describe('isStale', () => {
  it('flags a run that stopped reporting progress', () => {
    expect(isStale(run(), 30)).toBe(true)
  })

  it('exempts a run waiting on a reviewer', () => {
    // The run reports no progress by design. Calling that a timeout marked
    // every approval left overnight as a failure.
    expect(isStale(run({ meta_summary: { pending_review_uuid: 'appr-9' } }), 30)).toBe(false)
  })

  it('leaves terminal runs alone', () => {
    expect(isStale(run({ status: 'completed' }), 30)).toBe(false)
  })

  it('does not flag a run inside the threshold', () => {
    expect(isStale(run({ last_updated_at: new Date().toISOString() }), 30)).toBe(false)
  })

  it('falls back to started_at when no update has landed', () => {
    expect(isStale(run({ last_updated_at: null }), 30)).toBe(true)
  })
})


describe('activeReviewUuid', () => {
  const MARKER = { pending_review_uuid: 'rev-1' }

  it('offers the review while the run is still parked on it', () => {
    expect(activeReviewUuid(run({ status: 'running', meta_summary: MARKER }))).toBe('rev-1')
    expect(activeReviewUuid(run({ status: 'queued', meta_summary: MARKER }))).toBe('rev-1')
  })

  it('stops offering it once the run is cancelled', () => {
    // _cancel_result rewrites the activity without touching meta_summary, so
    // the marker outlives the run. Reading it alone left a cancelled row
    // rendering the clipboard icon, a clock, "Awaiting approval", and a click
    // through to a review nobody could act on.
    expect(activeReviewUuid(run({ status: 'canceled', meta_summary: MARKER }))).toBeNull()
  })

  it('stops offering it once the run has failed', () => {
    // The marker is stamped before the notify step, so a failure raised after
    // it keeps the marker — and the row suppressed its own error text in
    // favour of the approval tooltip.
    expect(activeReviewUuid(run({ status: 'failed', meta_summary: MARKER }))).toBeNull()
  })

  it('stops offering it once the run has completed', () => {
    expect(activeReviewUuid(run({ status: 'completed', meta_summary: MARKER }))).toBeNull()
  })

  it('is null for a live run that was never paused', () => {
    expect(activeReviewUuid(run({ status: 'running' }))).toBeNull()
  })
})
