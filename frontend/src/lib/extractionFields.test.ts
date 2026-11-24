import { describe, expect, it } from 'vitest'
import { inlineExtractionFields, withInlineExtractionFields, withoutInlineExtractionFields } from './extractionFields'

// The same rows are in backend/tests/test_workflow_legacy_extraction_fields.py,
// where they are also run through the engine.
const CASES: Array<[Record<string, unknown>, string[]]> = [
  // Every stored form.
  [{ searchphrases: 'PI Name, Sponsor/Funder,  Award Number ,' }, ['PI Name', 'Sponsor/Funder', 'Award Number']],
  [{ searchphrases: ['A', '', ' B '] }, ['A', 'B']],
  [{ keys: ['Start Date', ' End Date '] }, ['Start Date', 'End Date']],
  [{ keys: 'A, B' }, ['A', 'B']],
  [{ extractions: ['Award Number', 'F&A Rate'] }, ['Award Number', 'F&A Rate']],
  [{ extractions: 'A, B' }, ['A', 'B']],
  // Order of preference: searchphrases, then keys, then extractions.
  [{ searchphrases: 'Old', keys: ['Older'], extractions: ['New'] }, ['Old']],
  [{ searchphrases: '', keys: ['Keys'], extractions: ['New'] }, ['Keys']],
  [{ keys: ['Older'], extractions: ['New'] }, ['Older']],
  // A list with nothing but blanks gives way to the next one.
  [{ searchphrases: ' , ', keys: [], extractions: ['New'] }, ['New']],
  [{ searchphrases: [''], extractions: ['New'] }, ['New']],
  [{ keys: [' '], extractions: ['New'] }, ['New']],
  // Blank entries are dropped; duplicates are kept as stored.
  [{ searchphrases: 'A,,B,' }, ['A', 'B']],
  [{ searchphrases: ['A', ''], extractions: ['New'] }, ['A']],
  [{ extractions: ['A', 'a', 'A'] }, ['A', 'a', 'A']],
  // A field stored with a description is read by its name.
  [{ extractions: [{ key: ' F&A Rate ', description: 'x' }, 'B'] }, ['F&A Rate', 'B']],
  [{ searchphrases: [{ key: 'A' }] }, ['A']],
  [{ extractions: [{ description: 'no name' }, { key: '' }, { key: { key: 'nested' } }, 'B'] }, ['B']],
  // A number becomes its text; anything else that is not a name is skipped.
  [{ extractions: [5, null, 'B'] }, ['5', 'B']],
  [{ searchphrases: [5, 'A'] }, ['5', 'A']],
  [{ extractions: [2.5, 3.0, true, false, ['x'], 'B'] }, ['2.5', '3', 'B']],
  // A value that is not a list or text holds no fields.
  [{ searchphrases: 5, extractions: ['N'] }, ['N']],
  [{ searchphrases: { a: 1 }, extractions: ['N'] }, ['N']],
  [{ extractions: null, searchphrases: 5, keys: {} }, []],
  [{}, []],
]

describe('a workflow extraction step\'s own fields', () => {
  it.each(CASES)('reads %j as the engine runs it', (data, expected) => {
    expect(inlineExtractionFields(data)).toEqual(expected)
  })

  it('never shows an object as a field name', () => {
    const shown = inlineExtractionFields({ extractions: [{ key: 'F&A Rate' }, { other: 1 }, undefined, NaN, Infinity] })
    expect(shown).toEqual(['F&A Rate'])
  })

  it('saves an edit so the engine runs the edited fields, not the old ones', () => {
    const before = { searchphrases: 'A, B', keys: ['A', 'B'], name: 'Pull fields', model: 'm' }
    const after = withInlineExtractionFields(before, ['A', 'C'])
    expect(after).toEqual({ extractions: ['A', 'C'], name: 'Pull fields', model: 'm' })
    expect(inlineExtractionFields(after)).toEqual(['A', 'C'])
    expect(before).toEqual({ searchphrases: 'A, B', keys: ['A', 'B'], name: 'Pull fields', model: 'm' })
    // Removing every field leaves none behind in any form.
    expect(inlineExtractionFields(withInlineExtractionFields(before, []))).toEqual([])
  })

  it('drops every inline list when a saved set takes over', () => {
    const after = withoutInlineExtractionFields({ searchphrases: 'A', keys: ['A'], extractions: ['A'], name: 'x' })
    expect(after).toEqual({ name: 'x' })
  })
})
