import { describe, it, expect } from 'vitest'
import { formatPageLocator } from './pageLocator'

// Scanned documents have no page structure to read: their text comes from OCR,
// and the backend estimates page boundaries by spreading the page count evenly
// across the text. Showing "p. 4" for one of those states a location the data
// can't support, so estimated pages are marked. See #603.
describe('formatPageLocator', () => {
  it('renders a measured page plainly', () => {
    expect(formatPageLocator(12, false)).toBe('p. 12')
  })

  it('marks an estimated page so a reader can see it is approximate', () => {
    expect(formatPageLocator(12, true)).toBe('p. ~12')
  })

  it('treats a missing approximate flag as measured', () => {
    // Citations stored before the flag existed carry no value for it.
    expect(formatPageLocator(12)).toBe('p. 12')
  })

  it('has no locator when there is no page', () => {
    expect(formatPageLocator(null)).toBeNull()
    expect(formatPageLocator(undefined)).toBeNull()
  })

  it('ignores a non-integer page rather than rendering "p. 1.5"', () => {
    expect(formatPageLocator(1.5)).toBeNull()
  })

  it('renders a page range when a spanning chunk could not be pinned to one page', () => {
    expect(formatPageLocator(2, false, 3)).toBe('p. 2–3')
    expect(formatPageLocator(2, true, 4)).toBe('p. ~2–4')
  })

  it('ignores a page_end that does not extend past the page', () => {
    expect(formatPageLocator(3, false, 3)).toBe('p. 3')
    expect(formatPageLocator(3, false, null)).toBe('p. 3')
  })
})
