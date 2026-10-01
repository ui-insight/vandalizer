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
