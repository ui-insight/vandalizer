import { describe, it, expect } from 'vitest'
import { expandSnippetRefs, markUsed } from './snippetRefs'
import type { Citation } from '../types/chat'

const cites: Citation[] = [
  { document_title: 'PAPPG.pdf', ref: 1, cite_label: 'PAPPG.pdf, p. ~54' },
  { document_title: 'PAPPG.pdf', ref: 2, cite_label: 'PAPPG.pdf, p. ~139' },
  { document_title: 'NIH_GPS.pdf', ref: 3, cite_label: 'NIH_GPS.pdf, p. 88' },
]

describe('expandSnippetRefs', () => {
  it('shows a snippet number as the citation it stands for', () => {
    expect(expandSnippetRefs('Up to 12 months [S2].', cites))
      .toBe('Up to 12 months [Source: PAPPG.pdf, p. ~139].')
  })

  it('expands grouped references', () => {
    expect(expandSnippetRefs('Both agree [S1, S3].', cites))
      .toBe('Both agree [Source: PAPPG.pdf, p. ~54; NIH_GPS.pdf, p. 88].')
  })

  it('leaves a number no snippet carries as written', () => {
    expect(expandSnippetRefs('Odd [S9].', cites)).toBe('Odd [S9].')
  })

  it('leaves text alone when there are no numbered snippets', () => {
    expect(expandSnippetRefs('Plain [S1].', [])).toBe('Plain [S1].')
  })
})

describe('markUsed', () => {
  it('marks only the cited numbers as used', () => {
    expect(markUsed(cites, [2]).map(c => c.used)).toEqual([false, true, false])
  })

  it('marks everything unused when nothing was cited', () => {
    expect(markUsed(cites, []).every(c => c.used === false)).toBe(true)
  })
})
