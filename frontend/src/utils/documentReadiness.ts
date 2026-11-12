import type { Document } from '../types/document'
import { isDocReady, stageCopy } from './processingStatus'

export type DocumentReadiness = {
  uuid: string
  title: string
  message: string | null
  /** Set when the document has no usable text: reading it failed, or was stopped. */
  state?: 'failed' | 'stopped'
}

export function documentReadinessState(doc: Partial<Document>): DocumentReadiness['state'] {
  if (doc.processing || doc.task_status !== 'error') return undefined
  return doc.extraction_stopped ? 'stopped' : 'failed'
}

/** Describes recorded input limits without treating completed processing as accuracy. */
export function documentReadinessMessage(doc: Pick<Document, 'processing' | 'task_status' | 'valid'> & Partial<Document>): string | null {
  if (!isDocReady(doc)) return `${stageCopy(doc.task_status).short} Text is still being prepared; wait before relying on results.`
  if (!doc.valid) return `Upload check failed. ${doc.validation_feedback || 'Open the file to inspect it before use.'}`
  if (doc.task_status === 'error' && doc.extraction_stopped) return 'Text extraction was stopped, so this file has no text yet. Open the file to retry extraction.'
  if (doc.task_status === 'error') return 'Text extraction failed. Open the file to retry extraction or upload a replacement.'
  if (doc.ingest_error) return 'Search indexing failed. Chat retrieval is unavailable; open the file to inspect its text.'
  if (doc.ingestion_warning_text) return `${doc.ingestion_warning_text} Answers may be incomplete; inspect the original.`
  if (doc.extraction_low_quality) return 'Text may be incomplete. Inspect the original before using answers or extracted values.'
  return null
}

export type DocumentIssueKind = 'failed_check' | 'stopped' | 'no_text' | 'not_indexed' | 'poor_text' | 'partial_text'

export type DocumentIssue = {
  kind: DocumentIssueKind
  /** Short badge text for a file row. */
  label: string
  /** The full reason, for hover and screen readers. */
  detail: string
  /** A failure blocks use of the file; a warning only limits it; neutral is
   *  something a person chose (they stopped the read), not something that broke. */
  tone: 'error' | 'warning' | 'neutral'
  /** True when re-running the upload pipeline can clear it. */
  retryable: boolean
}

type IssueDoc = Pick<Document, 'processing' | 'task_status' | 'valid'> & Partial<Document>

/** The one issue a file row shows, most blocking first. Null while the file
 *  is still processing, and for a file with nothing wrong. */
export function documentIssue(doc: IssueDoc): DocumentIssue | null {
  if (!isDocReady(doc)) return null
  if (!doc.valid) {
    return {
      kind: 'failed_check', label: 'Failed check', tone: 'error', retryable: false,
      detail: doc.validation_feedback
        ? `Failed validation: ${doc.validation_feedback}`
        : 'This document did not pass automated upload validation.',
    }
  }
  if (doc.task_status === 'error' && doc.extraction_stopped) {
    return {
      kind: 'stopped', label: 'Stopped', tone: 'neutral', retryable: true,
      detail: 'Text extraction was stopped, so this document has no text yet. Retry to read it again.',
    }
  }
  if (doc.task_status === 'error') {
    // error_retryable false: the file itself is the problem (damaged, or a
    // format that can't be read), so a retry would fail the same way.
    const retryable = doc.error_retryable !== false
    return {
      kind: 'no_text', label: 'No text', tone: 'error', retryable,
      detail: doc.error_message
        ? `Text extraction failed: ${doc.error_message}`
        : `Text extraction failed for this document — chat and extraction cannot read it. ${retryable ? 'Try Retry extraction or re-upload it.' : 'Upload a replacement.'}`,
    }
  }
  if (doc.ingest_error) {
    return {
      kind: 'not_indexed', label: 'Not indexed', tone: 'warning', retryable: true,
      detail: `Could not index this document for search: ${doc.ingest_error}. Chat and Knowledge Base retrieval will not work.`,
    }
  }
  if (doc.extraction_low_quality) {
    return {
      kind: 'poor_text', label: 'Poor text', tone: 'warning', retryable: true,
      detail: 'Text extracted poorly from this document — most of its stored text is unreadable, so chat answers about it are likely to be unreliable. Try Retry extraction or re-upload it.',
    }
  }
  if (doc.ingestion_warning_text) {
    return {
      kind: 'partial_text', label: 'Partial text', tone: 'warning', retryable: false,
      detail: `This document was ingested with a caveat: ${doc.ingestion_warning_text}. Answers about it may be incomplete.`,
    }
  }
  return null
}

const ISSUE_ORDER: DocumentIssueKind[] = ['failed_check', 'no_text', 'stopped', 'not_indexed', 'poor_text', 'partial_text']
const ISSUE_SUMMARY: Record<DocumentIssueKind, string> = {
  failed_check: 'failed check',
  no_text: 'no text',
  stopped: 'stopped',
  not_indexed: 'not indexed',
  poor_text: 'poor text',
  partial_text: 'partial text',
}

/** Count per issue type across a file list, e.g. "4 not indexed · 1 no text".
 *  Null when no file has an issue. */
export function documentIssueSummary(docs: IssueDoc[]): string | null {
  const counts = new Map<DocumentIssueKind, number>()
  for (const doc of docs) {
    const issue = documentIssue(doc)
    if (issue) counts.set(issue.kind, (counts.get(issue.kind) ?? 0) + 1)
  }
  if (!counts.size) return null
  return ISSUE_ORDER.filter(kind => counts.has(kind)).map(kind => `${counts.get(kind)} ${ISSUE_SUMMARY[kind]}`).join(' · ')
}
