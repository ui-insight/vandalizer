import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { RawTextModal } from './RawTextModal'
import type { PollStatusResponse } from '../../types/document'

vi.mock('../../api/documents', () => ({
  pollStatus: vi.fn(),
  retryExtraction: vi.fn(),
  cancelExtraction: vi.fn(),
}))

import { cancelExtraction, pollStatus, retryExtraction } from '../../api/documents'
import { ApiError } from '../../api/client'

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

describe('RawTextModal Export Markdown', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
  })

  it('downloads the extracted text as a .md file named after the document', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ raw_text: '# Heading\n\nBody', title: 'Report.pdf' }))
    const createObjectURL = vi.fn((_blob: Blob) => 'blob:md')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('Report.md')
      expect(this.href).toBe('blob:md')
    })

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /export markdown/i }))

    expect(clickSpy).toHaveBeenCalledTimes(1)
    const blob = createObjectURL.mock.calls[0][0]
    expect(await blob.text()).toBe('# Heading\n\nBody')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:md')
    clickSpy.mockRestore()
  })

  it('is not offered when there is no text', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({
      status: 'error', raw_text: '', error_message: 'failed',
    }))
    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    await screen.findByText('failed')
    expect(screen.queryByRole('button', { name: /export markdown/i })).toBeNull()
  })
})

describe('RawTextModal Stop', () => {
  beforeEach(() => {
    vi.mocked(pollStatus).mockReset()
    vi.mocked(cancelExtraction).mockReset()
  })

  it('stops an in-flight extraction and then offers Retry', async () => {
    vi.mocked(pollStatus)
      .mockResolvedValueOnce(pollResponse({ status: 'ocr', processing: true, complete: false, raw_text: '' }))
      .mockResolvedValueOnce(pollResponse({
        status: 'error', processing: false, raw_text: '',
        error_message: 'Text extraction was stopped. Retry to read this document again.',
        error_retryable: true,
      }))
    vi.mocked(cancelExtraction).mockResolvedValue({ uuid: 'doc-1', status: 'error' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    expect(await screen.findByText(/Extracting text from your document/i)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /^stop$/i }))

    await waitFor(() => expect(cancelExtraction).toHaveBeenCalledWith('doc-1'))
    expect(await screen.findByText(/extraction was stopped/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /retry extraction/i })).toBeTruthy()
  })

  it('shows a stopped first read as Stopped, not as a failure', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({
      status: 'error', processing: false, raw_text: '', extraction_stopped: true,
      error_message: 'Text extraction was stopped. Retry to read this document again.',
      error_retryable: true,
    }))
    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    expect(await screen.findByText('Text extraction stopped')).toBeTruthy()
    expect(screen.queryByText('Text extraction failed')).toBeNull()
    expect(screen.getByRole('button', { name: /retry extraction/i })).toBeTruthy()
  })

  it('keeps showing the previous text when a re-run is stopped (support ticket)', async () => {
    // Re-run OCR on a document that read fine, then Stop: the server puts
    // the old text back, and the window says so instead of showing an error.
    vi.mocked(pollStatus)
      .mockResolvedValueOnce(pollResponse({ status: 'ocr', processing: true, complete: false, raw_text: '' }))
      .mockResolvedValueOnce(pollResponse({ raw_text: 'The text it had before.' }))
    vi.mocked(cancelExtraction).mockResolvedValue({ uuid: 'doc-1', status: 'restored', restored_previous_text: true })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /^stop$/i }))

    expect(await screen.findByText('The text it had before.')).toBeTruthy()
    expect(screen.getByRole('status')).toHaveTextContent('Stopped. This document still has the text it had before.')
    expect(screen.queryByText(/Text extraction (failed|stopped)/)).toBeNull()
  })

  it('does nothing when the confirmation is cancelled', async () => {
    vi.mocked(pollStatus).mockResolvedValue(pollResponse({ status: 'ocr', processing: true, complete: false, raw_text: '' }))
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /^stop$/i }))
    expect(cancelExtraction).not.toHaveBeenCalled()
  })

  it('treats a 409 (finished meanwhile) as no error and just reloads', async () => {
    vi.mocked(pollStatus)
      .mockResolvedValueOnce(pollResponse({ status: 'ocr', processing: true, complete: false, raw_text: '' }))
      .mockResolvedValueOnce(pollResponse({ raw_text: 'Done text' }))
    vi.mocked(cancelExtraction).mockRejectedValue(new ApiError(409, 'No extraction is in progress'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<RawTextModal docUuid="doc-1" onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /^stop$/i }))
    expect(await screen.findByText('Done text')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
