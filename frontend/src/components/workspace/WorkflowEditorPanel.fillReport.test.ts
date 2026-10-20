import { describe, expect, it } from 'vitest'
import {
  fileDownloadSummary, fillReportSummary, isFileDownloadPayload, tracedValueRows, tracedValuesSummary,
  type FillReportField,
} from './WorkflowEditorPanel'

describe('tracedValueRows', () => {
  const supported = { quote: 'Date: 2025-03-14', page: null, document_uuid: 'e1', document_title: 'Expense.txt', verified: true, value_supported: true, support: 'supported' }
  const missing = { quote: null, page: null, document_uuid: null, document_title: null, verified: false, support: 'unverified' }

  it('pairs an unwrapped single output with its one sidecar entry', () => {
    const rows = tracedValueRows({ date: '2025-03-14', vendor: 'Forestry Suppliers' }, [{ date: supported, vendor: missing }])
    expect(rows.map(r => [r.record, r.field, r.value])).toEqual([[1, 'date', '2025-03-14'], [1, 'vendor', 'Forestry Suppliers']])
    expect(tracedValuesSummary(rows)).toBe('1 of 2 values traced to a passage in a document')
  })

  it('keeps each record with its own sources, skipping outputs without any', () => {
    // A step of [Prompt, Extraction]: the prompt's slot holds an empty sidecar.
    const rows = tracedValueRows(['summary text', { date: '2025-03-14' }], [{}, { date: supported }])
    expect(rows.map(r => [r.record, r.field, r.value])).toEqual([[2, 'date', '2025-03-14']])
  })

  it('is empty when there is no sidecar', () => {
    expect(tracedValueRows({ a: 1 }, undefined)).toEqual([])
    expect(tracedValueRows('text', null)).toEqual([])
  })
})

describe('file_download payloads', () => {
  it('recognises the payload shape and summarises it instead of dumping base64', () => {
    const payload = { type: 'file_download', filename: 'budget-filled.pdf', file_type: 'pdf', data_b64: 'A'.repeat(4 * 10 * 1024) }
    expect(isFileDownloadPayload(payload)).toBe(true)
    expect(isFileDownloadPayload({ type: 'other' })).toBe(false)
    expect(isFileDownloadPayload('text')).toBe(false)
    expect(fileDownloadSummary(payload)).toBe('budget-filled.pdf (PDF, 30 KB)')
  })
})

describe('fillReportSummary', () => {
  it('counts found / not in input / not written / unfilled', () => {
    const fields: FillReportField[] = [
      { name: 'a', status: 'supported' },
      { name: 'b', status: 'supported' },
      { name: 'c', status: 'unsupported' },
      { name: 'd', status: 'not_written' },
      { name: 'e', status: 'missing' },
    ]
    expect(fillReportSummary(fields)).toBe('2 of 4 filled values found in the input · 1 not in the input · 1 not written · 1 unfilled')
  })

  it('reads cleanly when everything checks out', () => {
    expect(fillReportSummary([{ name: 'a', status: 'supported' }])).toBe('1 of 1 filled value found in the input')
  })
})
