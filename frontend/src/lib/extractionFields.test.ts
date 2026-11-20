import { describe, expect, it } from 'vitest'
import { inlineExtractionFields, withInlineExtractionFields, withoutInlineExtractionFields } from './extractionFields'

describe('a workflow extraction step\'s own fields', () => {
  it('shows fields stored the older way, as the catalog workflows store them', () => {
    // Seeded as one comma-separated string; the editor showed no fields.
    expect(inlineExtractionFields({ searchphrases: 'PI Name, Sponsor/Funder,  Award Number ,' }))
      .toEqual(['PI Name', 'Sponsor/Funder', 'Award Number'])
    expect(inlineExtractionFields({ keys: ['Start Date', ' End Date '] })).toEqual(['Start Date', 'End Date'])
    expect(inlineExtractionFields({ searchphrases: ['A', '', 'B'] })).toEqual(['A', 'B'])
  })

  it('reads the list the editor writes', () => {
    expect(inlineExtractionFields({ extractions: ['Award Number', 'F&A Rate'] })).toEqual(['Award Number', 'F&A Rate'])
  })

  it('shows what the engine will run when more than one list is present', () => {
    // workflow_engine.ExtractionNode: searchphrases, then keys, then extractions.
    expect(inlineExtractionFields({ searchphrases: 'Old', keys: ['Older'], extractions: ['New'] })).toEqual(['Old'])
    expect(inlineExtractionFields({ searchphrases: '', keys: ['Keys'], extractions: ['New'] })).toEqual(['Keys'])
    expect(inlineExtractionFields({ searchphrases: ' , ', keys: [], extractions: ['New'] })).toEqual(['New'])
  })

  it('is empty for a step with no fields or with junk', () => {
    for (const data of [{}, { extractions: null }, { searchphrases: 5 }, { keys: {} }, { extractions: [null, ''] }]) {
      expect(inlineExtractionFields(data as Record<string, unknown>)).toEqual([])
    }
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
