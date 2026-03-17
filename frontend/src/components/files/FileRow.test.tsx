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
    // The Loader2 icon has animate-spin class; check for the status text
    expect(screen.getByText('readying')).toBeTruthy()
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
})
