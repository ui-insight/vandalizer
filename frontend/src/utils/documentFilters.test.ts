import { describe, expect, it } from 'vitest'
import type { Document } from '../types/document'
import { documentFilterCounts, matchesDocumentFilter, visibleDocumentFilters } from './documentFilters'

const doc = (extension: string, extra: Partial<Document> = {}) =>
  ({ extension, processing: false, valid: true, task_status: 'complete', ...extra }) as Document

describe('document filters', () => {
  it('groups every uploadable type under PDF, Spreadsheet or Document', () => {
    expect(['pdf'].every(e => matchesDocumentFilter(doc(e), 'pdf'))).toBe(true)
    expect(['xls', 'xlsx', 'csv'].every(e => matchesDocumentFilter(doc(e), 'spreadsheet'))).toBe(true)
    expect(['doc', 'docx', 'txt', 'md'].every(e => matchesDocumentFilter(doc(e), 'document'))).toBe(true)
  })

  it('counts as needing attention exactly the files that show a problem badge', () => {
    const failed = doc('pdf', { task_status: 'error' })
    const notIndexed = doc('pdf', { ingest_error: 'timeout' })
    const stillReading = doc('pdf', { processing: true, task_status: 'extracting' })
    expect(matchesDocumentFilter(failed, 'attention')).toBe(true)
    expect(matchesDocumentFilter(notIndexed, 'attention')).toBe(true)
    expect(matchesDocumentFilter(stillReading, 'attention')).toBe(false)
    expect(matchesDocumentFilter(doc('pdf'), 'attention')).toBe(false)
  })

  it('counts each chip', () => {
    const counts = documentFilterCounts([doc('pdf'), doc('pdf', { task_status: 'error' }), doc('xlsx'), doc('docx')])
    expect(counts).toEqual({ all: 4, pdf: 2, spreadsheet: 1, document: 1, attention: 1 })
  })

  it('offers only chips that would narrow the list', () => {
    expect(visibleDocumentFilters(documentFilterCounts([doc('pdf'), doc('xlsx')]))).toEqual(['all', 'pdf', 'spreadsheet'])
    // One type and nothing wrong: a chip row would change nothing.
    expect(visibleDocumentFilters(documentFilterCounts([doc('pdf'), doc('pdf')]))).toEqual([])
    // One type, but a problem worth isolating.
    expect(visibleDocumentFilters(documentFilterCounts([doc('pdf'), doc('pdf', { ingest_error: 'x' })]))).toEqual(['all', 'attention'])
  })
})
