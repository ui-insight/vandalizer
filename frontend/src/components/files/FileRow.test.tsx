import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FileRow } from './FileRow'
import type { Document } from '../../types/document'

function makeDoc(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-id-1',
    title: 'Test Document.pdf',
    uuid: 'doc-uuid-1',
    extension: 'pdf',
    processing: false,
    valid: true,
    task_status: 'complete',
    folder: '0',
    created_at: '2025-01-01T12:00:00',
    updated_at: '2025-01-02T12:00:00',
    token_count: 500,
    num_pages: 5,
    classification: null,
    classification_confidence: null,
    classified_at: null,
    classified_by: null,
    retention_hold: false,
    soft_deleted: false,
    ...overrides,
  }
}

function renderFileRow(props: Partial<Parameters<typeof FileRow>[0]> = {}) {
  const defaults = {
    doc: makeDoc(),
    onContextMenu: vi.fn(),
    ...props,
  }
  return render(
    <table>
      <tbody>
        <FileRow {...defaults} />
      </tbody>
    </table>,
  )
}

describe('FileRow', () => {
  it('renders document title', () => {
    renderFileRow({ doc: makeDoc({ title: 'Annual Report 2025.pdf' }) })
    expect(screen.getByText('Annual Report 2025.pdf')).toBeTruthy()
  })

  it('shows classification badge for non-unrestricted docs', () => {
    renderFileRow({ doc: makeDoc({ classification: 'ferpa' }) })
    expect(screen.getByText('ferpa')).toBeTruthy()
    // The badge should have a title attribute
    expect(screen.getByTitle('Classification: ferpa')).toBeTruthy()
  })

  it('does not show classification badge for unrestricted docs', () => {
    renderFileRow({ doc: makeDoc({ classification: 'unrestricted' }) })
    expect(screen.queryByTitle(/Classification/)).toBeNull()
  })

  it('shows processing spinner when doc.processing=true', () => {
    renderFileRow({ doc: makeDoc({ processing: true, task_status: 'readying' }) })
    // The Loader2 icon has animate-spin class; the column shows a friendly
    // label rather than the raw pipeline stage name.
    expect(screen.getByText('Indexing…')).toBeTruthy()
    expect(screen.queryByText('readying')).toBeNull()
  })

  it('shows spinner during RAG indexing even when processing flips off', () => {
    // The backend pipeline flips `processing` off after text extraction but
    // keeps `task_status` on "readying" while indexing for retrieval. The
    // row must keep its spinner so users don't think the doc is fully ready.
    renderFileRow({ doc: makeDoc({ processing: false, task_status: 'readying' }) })
    expect(screen.getByText('Indexing…')).toBeTruthy()
  })

  it('treats task_status=complete with processing=false as ready', () => {
    renderFileRow({ doc: makeDoc({ processing: false, task_status: 'complete' }) })
    expect(screen.queryByText(/Indexing|Reading|Processing/)).toBeNull()
  })

  it('checkbox calls onToggleSelect', () => {
    const onToggleSelect = vi.fn()
    renderFileRow({
      doc: makeDoc({ uuid: 'sel-uuid' }),
      onToggleSelect,
      selected: false,
    })

    const checkbox = screen.getByRole('checkbox')
    fireEvent.click(checkbox)
    expect(onToggleSelect).toHaveBeenCalledWith('sel-uuid')
  })

  it('does not render checkbox when onToggleSelect is undefined', () => {
    renderFileRow({ onToggleSelect: undefined })
    expect(screen.queryByRole('checkbox')).toBeNull()
  })

  it('shows validation_feedback in tooltip when doc.valid=false', () => {
    renderFileRow({
      doc: makeDoc({
        valid: false,
        validation_feedback: 'Document appears to be empty or unreadable.',
      }),
    })
    expect(
      screen.getByTitle('Failed validation: Document appears to be empty or unreadable.'),
    ).toBeTruthy()
  })

  it('shows generic explanation when doc.valid=false and feedback is missing', () => {
    renderFileRow({ doc: makeDoc({ valid: false, validation_feedback: null }) })
    expect(
      screen.getByTitle('This document did not pass automated upload validation.'),
    ).toBeTruthy()
  })

  it('does not show validation warning when doc.valid=true', () => {
    renderFileRow({ doc: makeDoc({ valid: true }) })
    expect(screen.queryByTitle(/validation/i)).toBeNull()
  })

  it('shows a low-quality extraction warning when flagged', () => {
    renderFileRow({ doc: makeDoc({ extraction_low_quality: true }) })
    expect(screen.getByTitle(/Text extracted poorly/)).toBeTruthy()
  })

  it('does not show the low-quality warning for clean documents', () => {
    renderFileRow({ doc: makeDoc({ extraction_low_quality: false }) })
    expect(screen.queryByTitle(/Text extracted poorly/)).toBeNull()
  })

  it('ingest_error outranks the low-quality warning (one icon slot)', () => {
    renderFileRow({
      doc: makeDoc({ ingest_error: 'chroma down', extraction_low_quality: true }),
    })
    expect(screen.getByTitle(/Could not index this document/)).toBeTruthy()
    expect(screen.queryByTitle(/Text extracted poorly/)).toBeNull()
  })

  // #803: these warnings were computed, stored and API-served but never
  // rendered — a 400-page package whose OCR gave up at page 30 showed as a
  // clean, unmarked row.
  it('shows an ingestion caveat when the backend reports one', () => {
    renderFileRow({
      doc: makeDoc({
        ingestion_warnings: ['partial_ocr'],
        ingestion_warning_text: 'only part of this document could be converted',
      }),
    })
    expect(screen.getByTitle(/only part of this document could be converted/)).toBeTruthy()
  })

  it('says nothing for a document ingested whole', () => {
    renderFileRow({ doc: makeDoc({ ingestion_warnings: [], ingestion_warning_text: '' }) })
    expect(screen.queryByTitle(/ingested with a caveat/)).toBeNull()
  })

  it('a hard failure outranks the ingestion caveat (one icon slot)', () => {
    renderFileRow({
      doc: makeDoc({
        task_status: 'error',
        ingestion_warning_text: 'only part of this document could be converted',
      }),
    })
    expect(screen.getByTitle(/Text extraction failed/)).toBeTruthy()
    expect(screen.queryByTitle(/ingested with a caveat/)).toBeNull()
  })
})
