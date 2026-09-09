import { describe, expect, it } from 'vitest'
import { citationLabel, injectCitationChips, matchCitation, normalizeCitation, renderCitedMarkdown } from './CitedMarkdown'
import type { WorkflowCitation } from '../../types/workflow'

const UG: WorkflowCitation = {
  document_title: '2 CFR Part 200 Subpart F -- Audit Requirements',
  page: 12,
  kb_title: 'OMB Uniform Guidance (2 CFR 200)',
  label: 'OMB Uniform Guidance (2 CFR 200) — 2 CFR Part 200 Subpart F -- Audit Requirements · p. 12',
  content: '§ 200.501 Audit requirements. A non-Federal entity that expends $1,000,000 or more…',
  chunk_id: 'ug-1', similarity: 0.83,
}
const OSP: WorkflowCitation = {
  document_title: 'APM 45.05 Cost Share',
  page: 3, page_end: 4,
  kb_title: 'UI OSP',
  label: 'UI OSP — APM 45.05 Cost Share · p. 3–4',
  content: 'Cost share commitments require approval by the dean…',
  chunk_id: 'osp-1',
}
const NO_PAGE: WorkflowCitation = {
  document_title: 'PAPPG.pdf',
  label: 'PAPPG.pdf',
  content_preview: 'old run, preview only',
}
const SOURCES = [UG, OSP, NO_PAGE]

describe('citationLabel / normalizeCitation', () => {
  it('rebuilds the label the backend uses when a run did not store one', () => {
    expect(citationLabel({ document_title: 'Subpart E', page: 40, kb_title: 'OMB UG' })).toBe('OMB UG — Subpart E · p. 40')
    expect(citationLabel({ document_title: 'Subpart E', page: 2, page_end: 3 })).toBe('Subpart E · p. 2–3')
  })

  it('makes dash, separator, and page-marker variations compare equal', () => {
    expect(normalizeCitation('OMB UG — Subpart E · p. 40')).toBe(normalizeCitation('OMB UG - Subpart E, page 40'))
    expect(normalizeCitation('Subpart E · p. ~40')).toBe(normalizeCitation('Subpart E · p. 40'))
  })
})

describe('matchCitation', () => {
  it('matches the label exactly as the model was shown it', () => {
    expect(matchCitation(UG.label!, SOURCES)).toBe(0)
    expect(matchCitation(OSP.label!, SOURCES)).toBe(1)
  })

  it('tolerates a dropped knowledge-base title and a different page marker', () => {
    expect(matchCitation('2 CFR Part 200 Subpart F -- Audit Requirements, page 12', SOURCES)).toBe(0)
    expect(matchCitation('APM 45.05 Cost Share · p. 4', SOURCES)).toBe(1)
  })

  it('does not link a citation whose page the passage does not cover', () => {
    expect(matchCitation('2 CFR Part 200 Subpart F -- Audit Requirements · p. 99', SOURCES)).toBeNull()
  })

  it('ignores ordinary bracketed text and bare numbers', () => {
    expect(matchCitation('sic', SOURCES)).toBeNull()
    expect(matchCitation('3', SOURCES)).toBeNull()
    expect(matchCitation('see Appendix B', SOURCES)).toBeNull()
  })

  it('matches a document with no page by title alone', () => {
    expect(matchCitation('PAPPG.pdf', SOURCES)).toBe(2)
  })
})

describe('injectCitationChips', () => {
  it('turns a matching citation into a chip and leaves the rest of the text alone', () => {
    const html = '<p>Audits are required above $1M [OMB Uniform Guidance (2 CFR 200) — 2 CFR Part 200 Subpart F -- Audit Requirements · p. 12].</p>'
    const out = injectCitationChips(html, SOURCES)
    expect(out).toContain('<button type="button" class="kb-cite" data-cite="0"')
    expect(out).toContain('<span class="kb-cite-n">1</span>')
    expect(out).toContain('2 CFR Part 200 Subpart F -- Audit Requirements · p. 12</button>.')
    expect(out).toMatch(/^<p>Audits are required above \$1M <button/)
  })

  it('splits several citations in one bracket into several chips', () => {
    const html = `<p>Both apply [${UG.label}; ${OSP.label}].</p>`
    const out = injectCitationChips(html, SOURCES)
    expect(out).toContain('data-cite="0"')
    expect(out).toContain('data-cite="1"')
  })

  it('leaves an unmatched bracket, code, and links untouched', () => {
    const html = '<p>See [Appendix B] and <code>[x]</code> and <a href="#">[link]</a>.</p>'
    expect(injectCitationChips(html, SOURCES)).toBe(html)
    const mixed = `<p>[${UG.label}; Appendix B]</p>`
    expect(injectCitationChips(mixed, SOURCES)).toBe(mixed)
  })

  it('escapes passage data rather than injecting it as HTML', () => {
    const nasty: WorkflowCitation = { document_title: '<img src=x onerror=alert(1)>', page: 1, label: 'evil · p. 1' }
    const out = injectCitationChips('<p>[evil · p. 1]</p>', [nasty])
    expect(out).not.toContain('<img')
    expect(out).toContain('&lt;img')
  })
})

describe('renderCitedMarkdown', () => {
  it('renders markdown and then chips', () => {
    const out = renderCitedMarkdown(`**Cost share** is required [${OSP.label}].`, SOURCES)
    expect(out).toContain('<strong>Cost share</strong>')
    expect(out).toContain('data-cite="1"')
  })

  it('is plain sanitized markdown when there are no sources', () => {
    expect(renderCitedMarkdown('a [b] c', [])).toBe('<p>a [b] c</p>\n')
  })
})
