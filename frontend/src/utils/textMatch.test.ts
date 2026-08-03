import { describe, expect, it } from 'vitest'
import { normalizeWithMap } from './textMatch'

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
