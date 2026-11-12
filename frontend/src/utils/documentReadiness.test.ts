import { describe, expect, it } from 'vitest'
import { documentReadinessMessage } from './documentReadiness'
const ready = { valid: true, processing: false, task_status: 'complete' }
describe('document input caveats', () => {
  it('does not interpret completed processing as a quality warning', () => {
    expect(documentReadinessMessage(ready)).toBeNull()
    expect(documentReadinessMessage({ ...ready, ingestion_warning_text: 'Only 30 pages were read.' })).toContain('Only 30 pages were read.')
  })
  it('shows active retry progress ahead of an old failure', () => {
    expect(documentReadinessMessage({ ...ready, processing: true, task_status: 'ocr', ingest_error: 'old error' })).toContain('Running OCR')
  })
  it('distinguishes extraction and retrieval failures from partial text', () => {
    expect(documentReadinessMessage({ ...ready, task_status: 'error' })).toContain('retry extraction')
    expect(documentReadinessMessage({ ...ready, ingest_error: 'unavailable' })).toContain('Chat retrieval is unavailable')
    expect(documentReadinessMessage({ ...ready, extraction_low_quality: true })).toContain('Inspect the original')
  })
})

describe('a stopped extraction', () => {
  it('is reported as stopped, apart from a failed one', async () => {
    const { documentReadinessMessage, documentReadinessState } = await import('./documentReadiness')
    const base = { processing: false, valid: true }
    const stopped = { ...base, task_status: 'error', extraction_stopped: true }
    const failed = { ...base, task_status: 'error' }
    expect(documentReadinessState(stopped)).toBe('stopped')
    expect(documentReadinessMessage(stopped)).toMatch(/was stopped/)
    expect(documentReadinessState(failed)).toBe('failed')
    expect(documentReadinessMessage(failed)).toMatch(/failed/)
    expect(documentReadinessState({ ...base, task_status: 'complete' })).toBeUndefined()
    // Still being read: not failed yet, whatever the last status said.
    expect(documentReadinessState({ ...stopped, processing: true })).toBeUndefined()
  })
})
