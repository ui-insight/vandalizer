import { describe, expect, it } from 'vitest'
import { SECTION_RE, citationLabel, citationLocator, findHighlights, injectCitationChips, matchCitation, matchSectionReference, normalizeCitation, renderCitedMarkdown, renderCitedText } from './CitedMarkdown'
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

  it('tells passages of a pageless source apart by their part', () => {
    const part = (n: number): WorkflowCitation => ({
      document_title: 'Subpart E—Cost Principles', kb_title: 'OMB UG', chunk_id: `e${n}`,
      label: `OMB UG — Subpart E—Cost Principles · part ${n}`, content: `passage ${n}`,
    })
    const parts = [part(9), part(45)]
    expect(matchCitation('OMB UG — Subpart E—Cost Principles · part 45', parts)).toBe(1)
    // Copied without the knowledge-base title, the part still decides.
    expect(matchCitation('Subpart E—Cost Principles · part 45', parts)).toBe(1)
    expect(matchCitation('Subpart E—Cost Principles · part 7', parts)).toBeNull()
  })

  it('tells a whole-section passage apart by its section', () => {
    const chunk: WorkflowCitation = {
      document_title: 'Subpart E—Cost Principles', kb_title: 'OMB UG', chunk_id: 'e10',
      label: 'OMB UG — Subpart E—Cost Principles · part 11', content: '… § 200.405 Allocable costs.',
    }
    const section = (n: string): WorkflowCitation => ({
      document_title: 'Subpart E—Cost Principles', kb_title: 'OMB UG', chunk_id: `s${n}`,
      label: `OMB UG — Subpart E—Cost Principles · § ${n}`, content: `§ ${n} …`,
    })
    const sources = [chunk, section('200.404'), section('200.405')]
    expect(matchCitation('OMB UG — Subpart E—Cost Principles · § 200.405', sources)).toBe(2)
    expect(matchCitation('Subpart E—Cost Principles · §200.405', sources)).toBe(2)
    expect(matchCitation('Subpart E—Cost Principles · § 200.406', sources)).toBeNull()
    const far: WorkflowCitation = { document_title: 'Part 31', chunk_id: 'f', label: 'FAR — Part 31 · § 31.205-6' }
    expect(matchCitation('Part 31 · § 31.205-6', [far])).toBe(0)
  })

  it('tells the parts of a section apart, and a part from the whole section', () => {
    const part = (section: string, n: number): WorkflowCitation => ({
      document_title: 'Subpart D—Post Federal Award Requirements', kb_title: 'OMB UG', chunk_id: `d${section}-${n}`,
      label: `OMB UG — Subpart D—Post Federal Award Requirements · § ${section} · part ${n}`, content: `passage ${n}`,
    })
    const appendix: WorkflowCitation = {
      document_title: '2 CFR Part 200 — Appendices I–XII', chunk_id: 'a4',
      label: '2 CFR Part 200 — Appendices I–XII · Appendix III · part 4', content: 'C. Determination…',
    }
    const sources = [part('200.306', 2), part('200.307', 2), part('200.307', 3), appendix]
    expect(matchCitation('OMB UG — Subpart D—Post Federal Award Requirements · § 200.307 · part 2', sources)).toBe(1)
    expect(matchCitation('Subpart D—Post Federal Award Requirements · §200.307 · part 3', sources)).toBe(2)
    // A bare part, or the whole section, is none of them.
    expect(matchCitation('Subpart D—Post Federal Award Requirements · part 2', sources)).toBeNull()
    expect(matchCitation('Subpart D—Post Federal Award Requirements · § 200.307', sources)).toBeNull()
    expect(matchCitation('2 CFR Part 200 — Appendices I–XII · Appendix III · part 4', sources)).toBe(3)
    expect(matchCitation('2 CFR Part 200 — Appendices I–XII · Appendix III · part 5', sources)).toBeNull()
    expect(citationLocator(sources[1])).toBe('§ 200.307 · part 2')
    expect(citationLocator(appendix)).toBe('Appendix III · part 4')
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

describe('section references', () => {
  const SEC_407: WorkflowCitation = {
    document_title: 'Subpart E—Cost Principles', page: 40, kb_title: 'OMB Uniform Guidance (2 CFR 200)',
    label: 'OMB Uniform Guidance (2 CFR 200) — Subpart E—Cost Principles · p. 40', chunk_id: 's407',
    content: '§ 200.407 Prior written approval (prior approval). Under any given Federal award, the reasonableness…',
  }
  const MENTIONS_407: WorkflowCitation = {
    document_title: 'Subpart C—Pre-Federal Award Requirements', page: 12, chunk_id: 'c1',
    label: 'Subpart C—Pre-Federal Award Requirements · p. 12',
    content: 'The recipient must request prior approvals from the Federal agency (see § 200.407 and § 200.308).',
  }
  const NO_TEXT: WorkflowCitation = { document_title: 'preview only', label: 'x', content_preview: '…' }

  it('finds section numbers in prose, with or without a CFR prefix', () => {
    const text = 'Prior approval is governed by 2 CFR 200.407(a) and § 200.308; amount 1240.00.'
    expect([...text.matchAll(SECTION_RE)].map(m => [m[0], m[1]])).toEqual([
      ['2 CFR 200.407(a)', '200.407'], ['§ 200.308', '200.308'], ['1240.00', '1240.00'],
    ])
  })

  it('links a named section to the passage that is that section, not one that cites it', () => {
    expect(matchSectionReference('200.407', [MENTIONS_407, SEC_407])).toBe(1)
    expect(matchSectionReference('200.308', [MENTIONS_407, SEC_407])).toBe(0)
    expect(matchSectionReference('200.999', [MENTIONS_407, SEC_407])).toBeNull()
    expect(matchSectionReference('200.407', [NO_TEXT])).toBeNull()
  })

  it('adds a compact chip after the reference and keeps the reference text', () => {
    const html = '<p>Prior approval is governed by 2 CFR 200.407(a) and § 200.308.</p>'
    const out = injectCitationChips(html, [MENTIONS_407, SEC_407])
    expect(out).toContain('2 CFR 200.407(a)<button type="button" class="kb-cite kb-cite-ref" data-cite="1"')
    expect(out).toContain('§ 200.308<button type="button" class="kb-cite kb-cite-ref" data-cite="0"')
    expect(out).toContain('<span class="kb-cite-n">2</span></button> and ')
  })

  it('does not link a number that is not a section in any passage', () => {
    const html = '<p>Amount 1240.00 on 2025-03-14; see 45 CFR 46.101.</p>'
    expect(injectCitationChips(html, [SEC_407])).toBe(html)
  })

  it('does not turn a bare figure into a chip because a passage contains the same number', () => {
    const RATE: WorkflowCitation = {
      document_title: 'F&A Rate Agreement', page: 2, chunk_id: 'r1', label: 'F&A Rate Agreement · p. 2',
      content: 'The negotiated on-campus research rate is 52.5 percent of MTDC.',
    }
    expect(injectCitationChips('<p>Charged at 52.5% of MTDC.</p>', [RATE])).toBe('<p>Charged at 52.5% of MTDC.</p>')
    // Named as a section, the same number links only to a passage that is one.
    expect(matchSectionReference('52.5', [RATE], { requireMarker: true })).toBeNull()
    expect(matchSectionReference('200.407', [SEC_407], { requireMarker: true })).toBe(0)
  })

  it('leaves a bracket citation alone when it already contains the section', () => {
    const html = `<p>Rule [${SEC_407.label}] applies.</p>`
    const out = injectCitationChips(html, [SEC_407])
    expect(out.match(/kb-cite/g)!.length).toBe(2) // one chip (class + kb-cite-n span), no second ref chip
    expect(out).not.toContain('kb-cite-ref')
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

  it('keeps model HTML sanitized next to a chip', () => {
    const out = renderCitedMarkdown(`<img src=x onerror="alert(1)"> Cost share [${OSP.label}].`, SOURCES)
    expect(out).toContain('data-cite="1"')
    expect(out).not.toContain('onerror')
  })
})

describe('findHighlights / citationLocator', () => {
  const passage = 'based on §§ 200.402 through 200.411.\n\n§ 200.404 Reasonable costs.\n\nA cost is reasonable if it does not exceed an amount that a prudent person would incur.'

  it('finds a verified excerpt across line breaks, dash and quote styles', () => {
    const [[a, b]] = findHighlights(passage, ['A cost is reasonable if it does not   exceed an amount'])
    expect(passage.slice(a, b)).toBe('A cost is reasonable if it does not exceed an amount')
    expect(findHighlights('the pre‑award costs “as approved”', ['pre-award costs "as approved"'])).toEqual([[4, 33]])
  })

  it('highlights each piece of an excerpt joined by an ellipsis', () => {
    const r = findHighlights(passage, ['§ 200.404 Reasonable costs. … a prudent person would incur'])
    expect(r.map(([a, b]) => passage.slice(a, b))).toEqual(['§ 200.404 Reasonable costs.', 'a prudent person would incur'])
  })

  it('merges overlapping excerpts and ignores ones not in the passage', () => {
    expect(findHighlights(passage, ['Reasonable costs.', '§ 200.404 Reasonable', 'not in here'])).toEqual([[38, 65]])
  })

  it('names a pageless passage by its part', () => {
    expect(citationLocator({ document_title: 'Subpart E', label: 'OMB UG — Subpart E · part 46' })).toBe('part 46')
    expect(citationLocator({ document_title: 'x.pdf', page: 4, label: 'x.pdf · p. 4' })).toBe('p. 4')
    expect(citationLocator({ document_title: 'x' })).toBeNull()
  })

  it('names a whole-section passage by its section, with its pages when it has them', () => {
    expect(citationLocator({ document_title: 'Subpart E', label: 'OMB UG — Subpart E · § 200.405' })).toBe('§ 200.405')
    expect(citationLocator({ document_title: 'UG.pdf', page: 7, page_end: 8, label: 'UG.pdf · § 200.405' })).toBe('§ 200.405 · p. 7–8')
    expect(citationLocator({ document_title: 'Part 31', label: 'Part 31 · § 31.205-6' })).toBe('§ 31.205-6')
  })

  it('marks a section chip with the section it names', () => {
    const SEC: WorkflowCitation = { document_title: 'Subpart E', label: 'Subpart E · part 46', content: '§ 200.421 Advertising and public relations.' }
    const out = injectCitationChips('<p>See 2 CFR 200.421.</p>', [SEC])
    expect(out).toContain('data-section="200.421"')
  })
})

describe('renderCitedText', () => {
  it('escapes the text, keeps it as written, and still adds chips', () => {
    const json = `{\n  "result": "<b>Allowable</b> [${OSP.label}]"\n}`
    const out = renderCitedText(json, SOURCES)
    expect(out).toContain('&lt;b&gt;Allowable&lt;/b&gt;')
    expect(out).toContain('{\n  "result"')
    expect(out).toContain('data-cite="1"')
  })
})
