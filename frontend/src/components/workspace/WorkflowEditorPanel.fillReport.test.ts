import { describe, expect, it } from 'vitest'
import {
  fileDownloadSummary, fillReportSummary, isFileDownloadPayload, type FillReportField,
} from './WorkflowEditorPanel'

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
