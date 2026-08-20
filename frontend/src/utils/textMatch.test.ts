import { describe, expect, it } from 'vitest'
import { citationAnchor, normalizeWithMap } from './textMatch'

describe('normalizeWithMap', () => {
  it('lowercases and collapses whitespace, mapping back to source offsets', () => {
    const { norm, map } = normalizeWithMap('  Hello\n\n  World  ')
    expect(norm).toBe('hello world')
    expect(map).toHaveLength(norm.length)
    expect(map[0]).toBe(2) // 'h' -> original 'H'
  })

  it('folds smart quotes and dash variants', () => {
    const { norm } = normalizeWithMap('“terms” — and ‘conditions’')
    expect(norm).toBe('"terms" - and \'conditions\'')
  })

  it('expands ligatures while keeping the map aligned', () => {
    const { norm, map } = normalizeWithMap('ﬁnal')
    expect(norm).toBe('final')
    expect(map[0]).toBe(0)
    expect(map[1]).toBe(0) // both expanded chars map to the ligature
    expect(map).toHaveLength(5)
  })

  it('folds non-breaking spaces to plain spaces', () => {
    const { norm } = normalizeWithMap('December 31, 2025')
    expect(norm).toBe('december 31, 2025')
  })

  it('drops soft hyphens and zero-width characters', () => {
    const { norm } = normalizeWithMap('co­operative​ plan')
    expect(norm).toBe('cooperative plan')
  })

  it('lets an LLM-quoted passage match a PDF text layer with different punctuation', () => {
    const pdfText = 'In the event of any inconsistency among the terms — “precedence” applies.'
    const quote = 'the terms - "precedence" applies.'
    const doc = normalizeWithMap(pdfText)
    const needle = normalizeWithMap(quote).norm
    const at = doc.norm.indexOf(needle)
    expect(at).toBeGreaterThan(-1)
    // Projected start lands on the real "the terms" in the original string
    expect(pdfText.slice(doc.map[at], doc.map[at] + 9)).toBe('the terms')
  })
})

describe('citationAnchor', () => {
  it('keeps a short preview whole, including its last word', () => {
    // The server cuts content_preview at 240 chars, so anything this short is
    // a complete chunk and its final word is not a fragment. Trimming it would
    // cost precision on the anchors least able to spare it.
    const preview = 'The recipient shall retain records for three years'
    expect(citationAnchor(preview)).toBe(preview)
  })

  it('keeps a short preview that ends on punctuation intact', () => {
    const preview = 'Records are retained for three years.'
    expect(citationAnchor(preview)).toBe(preview)
  })

  it('drops the partial word a genuinely truncated preview ends on', () => {
    // A real server-side cut lands at 240 chars, past the cap, so the anchor
    // comes from the >120 branch and ends on a whole word.
    const preview = 'The recipient shall retain records for three years '.repeat(5).slice(0, 240)
    const anchor = citationAnchor(preview)
    expect(anchor.length).toBeLessThanOrEqual(120)
    expect(anchor.endsWith('yea')).toBe(false)
    expect(preview.startsWith(anchor)).toBe(true)
  })

  it('caps a long preview at a word boundary', () => {
    const preview = 'alpha '.repeat(60)
    const anchor = citationAnchor(preview)
    expect(anchor.length).toBeLessThanOrEqual(120)
    expect(anchor.endsWith('alpha')).toBe(true)
    expect(preview.trim().startsWith(anchor)).toBe(true)
  })

  it('collapses whitespace so the needle matches reflowed document text', () => {
    expect(citationAnchor('  two   lines\nof text.  ')).toBe('two lines of text.')
  })

  it('returns nothing usable for an empty or missing preview', () => {
    expect(citationAnchor('   ')).toBe('')
    expect(citationAnchor(undefined)).toBe('')
  })

  it('keeps an unbroken run rather than emptying the anchor', () => {
    const url = 'https://example.gov/' + 'a'.repeat(200)
    expect(citationAnchor(url)).toBe(url.slice(0, 120))
  })
})
