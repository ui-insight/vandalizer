import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { RawTextModal } from './RawTextModal'
import type { PollStatusResponse } from '../../types/document'

vi.mock('../../api/documents', () => ({
  pollStatus: vi.fn(),
  retryExtraction: vi.fn(),
}))

import { pollStatus, retryExtraction } from '../../api/documents'

function pollResponse(overrides: Partial<PollStatusResponse> = {}): PollStatusResponse {
  return {
    status: 'complete',
    status_messages: [],
    complete: true,
    raw_text: 'Some extracted text.',
    validation_feedback: null,
    valid: true,
    path: 'uploads/doc.pdf',
    error_message: null,
    processing: false,
    title: 'Doc.pdf',
    ...overrides,
  }
}

describe('RawTextModal low-quality notice', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
    vi.mocked(retryExtraction).mockReset()
  })

  it('offers Retry extraction when the extraction succeeded but reads as garbage', async () => {
    // The document is "complete" with text, so the error branch — previously
    // the only place the retry button lived — never renders for it.
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ extraction_low_quality: true }))
    vi.mocked(retryExtraction).mockResolvedValue({} as never)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)

    const button = await screen.findByRole('button', { name: /retry extraction/i })
    expect(screen.getByText(/most of the stored text is unreadable/i)).toBeTruthy()

    fireEvent.click(button)
    await waitFor(() => expect(retryExtraction).toHaveBeenCalledWith('doc-1', { forceOcr: false }))
  })

  it('shows no notice for a document that extracted cleanly', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ extraction_low_quality: false }))

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)

    await screen.findByText(/Extracted Text/i)
    await waitFor(() => expect(pollStatus).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: /retry extraction/i })).toBeNull()
    expect(screen.queryByText(/most of the stored text is unreadable/i)).toBeNull()
  })
})

describe('RawTextModal extraction failure', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
  })

  it('offers no Retry when the file itself is the problem', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({
      status: 'error', raw_text: '', error_message: 'This workbook is damaged', error_retryable: false,
    }))
    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    expect(await screen.findByText('This workbook is damaged')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /retry extraction/i })).toBeNull()
  })

  it('still offers Retry for a failure that may be temporary', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({
      status: 'error', raw_text: '', error_message: 'Text extraction failed: timeout',
    }))
    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    expect(await screen.findByRole('button', { name: /retry extraction/i })).toBeTruthy()
  })
})

describe('RawTextModal Re-run OCR', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
    vi.mocked(retryExtraction).mockReset()
    vi.restoreAllMocks()
  })

  it('re-runs OCR on a healthy PDF after confirmation', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ extension: 'pdf' }))
    vi.mocked(retryExtraction).mockResolvedValue({} as never)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /re-run ocr/i }))

    await waitFor(() => expect(retryExtraction).toHaveBeenCalledWith('doc-1', { forceOcr: true }))
  })

  it('does nothing when the confirmation is cancelled', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ extension: 'pdf' }))
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /re-run ocr/i }))

    expect(retryExtraction).not.toHaveBeenCalled()
  })

  it('is not offered for non-PDF documents', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ extension: 'docx', path: 'uploads/doc.docx' }))

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    await screen.findByText('Some extracted text.')

    expect(screen.queryByRole('button', { name: /re-run ocr/i })).toBeNull()
  })
})

