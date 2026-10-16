import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { SpreadsheetViewer } from './SpreadsheetViewer'
import type { PollStatusResponse } from '../../types/document'

vi.mock('../../api/documents', () => ({
  pollStatus: vi.fn(),
  retryExtraction: vi.fn(),
}))
vi.mock('../../api/files', () => ({
  fetchSheetJson: vi.fn(),
  downloadFileUrl: (id: string) => `/api/files/download?docid=${id}`,
}))

import { pollStatus, retryExtraction } from '../../api/documents'
import { fetchSheetJson } from '../../api/files'

const DAMAGED =
  "This workbook is damaged — part of its contents (xl/workbook.xml) is cut off or corrupted — so it can't be read."

function status(overrides: Partial<PollStatusResponse> = {}): PollStatusResponse {
  return {
    status: 'complete', status_messages: [], complete: true, raw_text: 'A1 Budget',
    validation_feedback: null, valid: true, path: 'u/doc.xlsx', error_message: null,
    processing: false, title: 'budget.xlsx', ...overrides,
  }
}

const SHEET = { sheets: [{ name: 'Sheet1', headers: ['A'], rows: [['Budget']] }] }

describe('SpreadsheetViewer extraction failures', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
    vi.mocked(retryExtraction).mockReset()
    vi.mocked(fetchSheetJson).mockReset()
  })

  it('a damaged workbook gets its reason, a download, and no Retry', async () => {
    vi.mocked(fetchSheetJson).mockRejectedValue(new Error(DAMAGED))
    vi.mocked(pollStatus).mockResolvedValue(status({
      status: 'error', raw_text: '', error_message: DAMAGED, error_retryable: false,
    }))
    render(<SpreadsheetViewer docUuid="doc-1" />)

    expect(await screen.findByText("This spreadsheet couldn't be read")).toBeTruthy()
    // Shown once, not twice, though the preview and extraction both report it.
    expect(screen.getAllByText(DAMAGED)).toHaveLength(1)
    expect(screen.getByRole('link', { name: /download/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /retry extraction/i })).toBeNull()
    expect(screen.queryByText('Sheet rendering not available')).toBeNull()
  })

  it('a temporary failure with no preview offers a working Retry', async () => {
    vi.mocked(fetchSheetJson).mockRejectedValue(new Error('Sheet rendering not available'))
    vi.mocked(pollStatus).mockResolvedValue(status({
      status: 'error', raw_text: '', error_message: 'Text extraction failed: worker restarted',
    }))
    vi.mocked(retryExtraction).mockResolvedValue({} as never)
    render(<SpreadsheetViewer docUuid="doc-1" />)

    const retry = await screen.findByRole('button', { name: /retry extraction/i })
    expect(screen.getByText('Text extraction failed: worker restarted')).toBeTruthy()
    expect(screen.queryByText('Sheet rendering not available')).toBeNull()
    fireEvent.click(retry)
    await waitFor(() => expect(retryExtraction).toHaveBeenCalledWith('doc-1'))
  })

  it('a sheet that renders but failed extraction says chat cannot read it, with Retry', async () => {
    vi.mocked(fetchSheetJson).mockResolvedValue(SHEET as never)
    vi.mocked(pollStatus).mockResolvedValue(status({
      status: 'error', raw_text: '', error_message: 'Text extraction failed: timeout',
    }))
    render(<SpreadsheetViewer docUuid="doc-1" />)

    expect(await screen.findByText('Text extraction failed')).toBeTruthy()
    expect(screen.getByText('Budget')).toBeTruthy()
    expect(screen.getByRole('button', { name: /retry extraction/i })).toBeTruthy()
  })

  it('a healthy spreadsheet shows no failure', async () => {
    vi.mocked(fetchSheetJson).mockResolvedValue(SHEET as never)
    vi.mocked(pollStatus).mockResolvedValue(status())
    render(<SpreadsheetViewer docUuid="doc-1" />)

    expect(await screen.findByText('Budget')).toBeTruthy()
    await waitFor(() => expect(pollStatus).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
