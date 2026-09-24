import { describe, expect, it } from 'vitest'
import { splitFieldTerms } from './extractionTerms'

describe('splitFieldTerms', () => {
  it('splits a comma-separated paste into separate terms', () => {
    expect(splitFieldTerms('PI Name, Institution, Total Budget')).toEqual([
      'PI Name', 'Institution', 'Total Budget',
    ])
  })

  it('keeps a single term whole', () => {
    expect(splitFieldTerms('  Award Number ')).toEqual(['Award Number'])
  })

  it('drops blanks, repeats and terms that already exist', () => {
    expect(splitFieldTerms('PI Name,, Sponsor ,PI Name, Sponsor', ['Sponsor'])).toEqual(['PI Name'])
  })
})
