import { describe, it, expect } from 'vitest'
import { highlightMissLabel } from './DocumentViewer'

// #626 made every page *label* hedge when the number was interpolated from OCR
// text ("p. ~12"). This is the one place that still stated such a page as fact,
// and it is the worst place for it: the fallback fires when the passage could
// not be matched, which happens disproportionately on scanned documents —
// the quote came out of OCR text while the search runs against the PDF's own
// text layer. #626's benchmark puts the interpolated page a median 6 pages off,
// correct 4.5% of the time on a 68-page proposal.

describe('highlightMissLabel', () => {
  it('states a measured page plainly', () => {
    expect(highlightMissLabel(12, false)).toBe('passage not matched — showing page 12')
  })

  it('hedges a page that was estimated from OCR text', () => {
    expect(highlightMissLabel(12, true)).toBe(
      'passage not matched — showing approximately page 12',
    )
  })

  it('never asserts an estimated page as exact', () => {
    const label = highlightMissLabel(234, true)
    expect(label).toContain('approximately')
    expect(label).not.toMatch(/showing page \d/)
  })

  it('says nothing about a page when there is none', () => {
    expect(highlightMissLabel(null, false)).toBe('not found in this document')
    expect(highlightMissLabel(undefined, true)).toBe('not found in this document')
  })

  it('treats page 0 as a real page rather than absent', () => {
    // `if (!page)` would swallow it; the guard is an explicit null check.
    expect(highlightMissLabel(0, false)).toBe('passage not matched — showing page 0')
  })
})
