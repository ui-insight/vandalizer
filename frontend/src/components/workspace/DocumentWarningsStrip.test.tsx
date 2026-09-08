import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DocumentWarningsStrip } from './ExtractionEditorPanel'

/**
 * #803: document_warnings were computed, stored and API-served but never
 * rendered, so an extraction over a half-converted package looked exactly
 * like one over a clean document.
 */
describe('DocumentWarningsStrip', () => {
  it('renders nothing when every document was read whole', () => {
    const { container } = render(<DocumentWarningsStrip warnings={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('names each document and what was wrong with it', () => {
    render(
      <DocumentWarningsStrip
        warnings={[{
          document_uuid: 'd1',
          title: 'NSF Award Package.pdf',
          codes: ['partial_ocr'],
          text: 'only part of this document could be converted',
        }]}
      />,
    )
    expect(screen.getByText(/One document was not read in full/)).toBeTruthy()
    expect(screen.getByText('NSF Award Package.pdf')).toBeTruthy()
    expect(
      screen.getByText(/only part of this document could be converted/),
    ).toBeTruthy()
  })

  it('pluralizes and lists every affected document', () => {
    render(
      <DocumentWarningsStrip
        warnings={[
          { document_uuid: 'd1', title: 'A.pdf', codes: ['partial_ocr'], text: 'partly converted' },
          { document_uuid: 'd2', title: 'B.pdf', codes: ['no_extractable_text'], text: 'could not be read' },
        ]}
      />,
    )
    expect(screen.getByText(/2 documents were not read in full/)).toBeTruthy()
    expect(screen.getByText('A.pdf')).toBeTruthy()
    expect(screen.getByText('B.pdf')).toBeTruthy()
  })

  it('survives a warning with no composed text', () => {
    render(
      <DocumentWarningsStrip
        warnings={[{ document_uuid: 'd1', title: 'C.pdf', codes: ['partial_ocr'] }]}
      />,
    )
    expect(screen.getByText('C.pdf')).toBeTruthy()
  })
})
