import type { Document } from '../types/document'
import { fileKind } from './fileDisplay'
import { documentIssue } from './documentReadiness'

/** The chips on the Files panel's Documents heading. */
export type DocumentFilter = 'all' | 'pdf' | 'spreadsheet' | 'document' | 'attention'

export const DOCUMENT_FILTER_LABELS: Record<DocumentFilter, string> = {
  all: 'All',
  pdf: 'PDF',
  spreadsheet: 'Spreadsheet',
  document: 'Document',
  attention: 'Needs attention',
}

/** Type chips, in display order. "Needs attention" is shown apart from them. */
export const TYPE_FILTERS: DocumentFilter[] = ['pdf', 'spreadsheet', 'document']

type FilterDoc = Pick<Document, 'extension' | 'processing' | 'task_status' | 'valid'> & Partial<Document>

/** "Needs attention" is any file that shows a problem badge — the same set
 *  the row badges and the issue summary count, so the three never disagree. */
export function matchesDocumentFilter(doc: FilterDoc, filter: DocumentFilter): boolean {
  switch (filter) {
    case 'all': return true
    case 'attention': return documentIssue(doc) !== null
    default: return fileKind(doc.extension) === filter
  }
}

export function documentFilterCounts(docs: FilterDoc[]): Record<DocumentFilter, number> {
  const counts: Record<DocumentFilter, number> = { all: 0, pdf: 0, spreadsheet: 0, document: 0, attention: 0 }
  for (const doc of docs) {
    counts.all++
    const kind = fileKind(doc.extension)
    if (kind === 'pdf' || kind === 'spreadsheet' || kind === 'document') counts[kind]++
    if (documentIssue(doc)) counts.attention++
  }
  return counts
}

/** The chips worth showing: a type chip only when the list holds that type,
 *  and none at all when they couldn't narrow the list (one type, no problems). */
export function visibleDocumentFilters(counts: Record<DocumentFilter, number>): DocumentFilter[] {
  const types = TYPE_FILTERS.filter(filter => counts[filter] > 0)
  const narrowingTypes = types.filter(filter => counts[filter] < counts.all)
  const chips: DocumentFilter[] = narrowingTypes.length ? ['all', ...types] : ['all']
  if (counts.attention > 0) chips.push('attention')
  return chips.length > 1 ? chips : []
}
