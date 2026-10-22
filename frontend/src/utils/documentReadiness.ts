import type { Document } from '../types/document'
import { isDocReady, stageCopy } from './processingStatus'

export type DocumentReadiness = { uuid: string; title: string; message: string | null }

/** Describes recorded input limits without treating completed processing as accuracy. */
export function documentReadinessMessage(doc: Pick<Document, 'processing' | 'task_status' | 'valid'> & Partial<Document>): string | null {
  if (!isDocReady(doc)) return `${stageCopy(doc.task_status).short} Text is still being prepared; wait before relying on results.`
  if (!doc.valid) return `Upload check failed. ${doc.validation_feedback || 'Open the file to inspect it before use.'}`
  if (doc.task_status === 'error') return 'Text extraction failed. Open the file to retry extraction or upload a replacement.'
  if (doc.ingest_error) return 'Search indexing failed. Chat retrieval is unavailable; open the file to inspect its text.'
  if (doc.ingestion_warning_text) return `${doc.ingestion_warning_text} Answers may be incomplete; inspect the original.`
  if (doc.extraction_low_quality) return 'Text may be incomplete. Inspect the original before using answers or extracted values.'
  return null
}
