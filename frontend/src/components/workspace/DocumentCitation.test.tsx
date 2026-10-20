import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ExtractionFieldSource } from '../../api/extractions'
import {
  DocumentCitationChip, citationFromFieldSource, citationFromFillReport, documentCitationLabel, valueRangeIn,
} from './DocumentCitation'

// The workspace the chip opens documents through; null outside a workspace.
const workspace = vi.hoisted(() => ({
  current: null as { setWorkspaceMode: (mode: string) => void; viewDocument: (...args: unknown[]) => void } | null,
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useOptionalWorkspace: () => workspace.current }))

const SOURCE: ExtractionFieldSource = {
  quote: 'Amount: $1,240.00', page: 1, document_uuid: 'exp-1', document_title: 'Expense_Record.txt',
  verified: true, value_supported: true, support: 'supported',
}

describe('citationFromFieldSource', () => {
  it('cites only a value the check found inside a passage located in a document', () => {
    expect(citationFromFieldSource(SOURCE, '$1,240.00')).toMatchObject({
      documentUuid: 'exp-1', page: 1, excerpt: 'Amount: $1,240.00', value: '$1,240.00', check: 'passage',
    })
    // The passage is real but does not hold the value: no chip.
    expect(citationFromFieldSource({ ...SOURCE, value_supported: false, support: 'quote_unsupported' }, '$9')).toBeNull()
    expect(citationFromFieldSource({ ...SOURCE, value_supported: null, support: 'unassessed' }, 'Yes')).toBeNull()
    expect(citationFromFieldSource({ ...SOURCE, verified: false, support: 'unverified' }, '$1,240.00')).toBeNull()
    // Nothing to open, or nothing to show.
    expect(citationFromFieldSource({ ...SOURCE, document_uuid: null }, '$1,240.00')).toBeNull()
    expect(citationFromFieldSource({ ...SOURCE, quote: '  ' }, '$1,240.00')).toBeNull()
  })

  it('reads an older source without the support field the cautious way', () => {
    const legacy = { ...SOURCE, support: undefined, value_supported: undefined }
    expect(citationFromFieldSource(legacy, '$1,240.00')).toBeNull()
  })
})

describe('citationFromFillReport', () => {
  it('drops the ellipses that mark where the report cut the document text', () => {
    const cite = citationFromFillReport({
      status: 'supported', value: '47%', document_uuid: 'd1', document_title: 'Rate agreement.pdf',
      page: 3, page_approximate: true, quote: '…negotiated rate is 47% of MTDC for on-campus…',
    })
    expect(cite).toMatchObject({ excerpt: 'negotiated rate is 47% of MTDC for on-campus', pageApproximate: true, check: 'search' })
    expect(documentCitationLabel(cite!)).toBe('Rate agreement.pdf · p. ~3')
  })

  it('cites nothing found only in the previous step, or not found at all', () => {
    expect(citationFromFillReport({ status: 'supported', value: 'x', quote: 'x y z' })).toBeNull()
    expect(citationFromFillReport({ status: 'unsupported', value: 'x', document_uuid: 'd1', quote: 'x' })).toBeNull()
  })
})

describe('valueRangeIn', () => {
  it('marks the occurrence nearest the middle, as a whole value', () => {
    const excerpt = 'Item 2 of 3: receivers (2) cost 12 each, 2 units'
    const [a, b] = valueRangeIn(excerpt, '2')!
    expect(excerpt.slice(a, b)).toBe('2')
    expect(a).toBe(excerpt.indexOf('(2)') + 1)
  })

  it('finds nothing when the value is written differently', () => {
    expect(valueRangeIn('Amount: $1,240.00', '1240.0')).toBeNull()
    expect(valueRangeIn('Award L24AC00293-00', 'L24AC0029')).toBeNull()
  })
})

describe('DocumentCitationChip', () => {
  beforeEach(() => { workspace.current = null })

  const cite = citationFromFieldSource(SOURCE, '$1,240.00')!

  it('shows the excerpt with the value marked, and no way in outside the workspace', () => {
    render(<DocumentCitationChip citation={cite} />)
    fireEvent.click(screen.getByRole('button', { name: 'Document source: Expense_Record.txt · p. 1' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('Passage the value was extracted from')
    expect(dialog.querySelector('mark')?.textContent).toBe('$1,240.00')
    expect(screen.queryByRole('button', { name: /Open/ })).toBeNull()
  })

  it('opens the document at the page with the excerpt to highlight', () => {
    const setWorkspaceMode = vi.fn()
    const viewDocument = vi.fn()
    workspace.current = { setWorkspaceMode, viewDocument }
    render(<DocumentCitationChip citation={cite} />)
    fireEvent.click(screen.getByRole('button', { name: /Document source/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Open at p. 1' }))
    expect(setWorkspaceMode).toHaveBeenCalledWith('files')
    expect(viewDocument).toHaveBeenCalledWith('exp-1', 'Expense_Record.txt', {
      terms: ['Amount: $1,240.00'], page: 1, pageApproximate: false,
    })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('closes on Escape', () => {
    render(<DocumentCitationChip citation={cite} />)
    fireEvent.click(screen.getByRole('button', { name: /Document source/ }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
