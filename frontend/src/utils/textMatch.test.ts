import { describe, expect, it } from 'vitest'
import { citationAnchor, findLoose, findLoosePrefix, normalizeWithMap, skeletonWithMap } from './textMatch'

describe('findLoose — a source quote against a PDF text layer', () => {
  // The text layers below are pdf.js's own, from the NSF NHERI and FFAR
  // Seeding Solutions PDFs; the needles are the stored source quotes.
  it('ignores the spacing a text layer puts between items', () => {
    const page = "Due Dates Letter of Intent Due Date(s)   (required)   (due by 5 p.m. proposer's local time) : October 16, 2015 Full"
    const quote = "Letter of Intent Due Date(s) (required) (due by 5 p.m. proposer's local time): October 16, 2015"
    expect(normalizeWithMap(page).norm.includes(normalizeWithMap(quote).norm)).toBe(false)
    const [[a, b]] = findLoose(page, quote)
    expect(page.slice(a, b)).toBe("Letter of Intent Due Date(s)   (required)   (due by 5 p.m. proposer's local time) : October 16, 2015")
  })

  it('ignores bullets and list marks', () => {
    const page = 'd components •   Project title ( up to 250 characters ) •   Key project personnel'
    const [[a, b]] = findLoose(page, '- Project title (up to 250 characters)')
    // From its first letter to its last: the bullet and the closing bracket are not compared.
    expect(page.slice(a, b)).toBe('Project title ( up to 250 characters')
  })

  it('finds a quote whose ligature the text extractor dropped', () => {
    const page = 'Section 7. Organizational Structure, Staffing, and Diversity (all proposals, up to two pages).'
    const [[a, b]] = findLoose(page, 'Section 7. Organizational Structure, Stang, and Diversity')
    expect(page.slice(a, b)).toBe('Section 7. Organizational Structure, Staffing, and Diversity')
  })

  it('reads a ligature glyph in the text layer as its letters', () => {
    expect(skeletonWithMap('Speciﬁc').skel).toBe('specific')
    const page = 'Section 11. Component-Speciﬁc Implementation (all proposals)'
    expect(findLoose(page, 'Component-Specific Implementation')).toHaveLength(1)
  })

  it('finds every place, and nothing that is not there', () => {
    const page = 'Project abstract (up to 500 words) and later Project abstract ( up to 500 words )'
    expect(findLoose(page, 'Project abstract (up to 500 words)')).toHaveLength(2)
    expect(findLoose(page, 'Project summary (up to 500 words)')).toEqual([])
  })

  it('leaves a short needle to the exact match: its letters could stand anywhere', () => {
    expect(findLoose('the F and A rate of the award', 'F&A rate')).toEqual([])
    expect(findLoose('Cost Sharing Requirements', 'Cost Sharing')).toEqual([])
    // Twelve letters and digits are enough: a component's word limit.
    expect(findLoose('the word limit. ( up to 5000 words) o Budget Form', '(up to 5000 words)')).toHaveLength(1)
  })
})

describe('findLoosePrefix — a passage that runs onto the next page', () => {
  it('finds as much of its start as the page has', () => {
    // FFAR Seeding Solutions, p. 6 ends mid-sentence; the quote goes on to p. 7.
    const page6 = 'A grantee may request a no-cost extension of up to 6 months to complete the work’s planned scope. ' +
      'The request must be communicated to FFAR and submitted through the Grant Management System at least thirty ' +
      '(30) days before the end date of the grant. The'
    const quote = "A grantee may request a no-cost extension of up to 6 months to complete the work's planned scope. The request " +
      'must be communicated to FFAR and submitted through the Grant Management System at least thirty (30) days before ' +
      'the end date of the grant. The request must justify the need for the extension'
    expect(findLoose(page6, quote)).toEqual([])
    const range = findLoosePrefix(page6, quote)
    expect(range).not.toBeNull()
    const [a, b] = range as [number, number]
    // Everything of it the page has: from its first word to the page's last.
    expect(page6.slice(a, b)).toBe(page6)
  })

  it('needs a few words of it at least', () => {
    expect(findLoosePrefix('The request must justify', 'Budget narrative: Provide a brief overview of the budget')).toBeNull()
  })
})

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

  it('lets a quote taken from the markdown text match the PDF text layer', () => {
    // Support ticket: Inspect source on FOA Number showed "passage not matched".
    const pdfText = 'Funding Opportunity\nFOA Number: PA-23-152 Parent R01'
    for (const quote of ['**FOA Number:** PA-23-152', '## FOA Number: PA-23-152', '| FOA Number: | `PA-23-152` |']) {
      const needle = normalizeWithMap(quote).norm
      expect(needle).toBe('foa number: pa-23-152')
      const doc = normalizeWithMap(pdfText)
      const at = doc.norm.indexOf(needle)
      expect(at).toBeGreaterThan(-1)
      expect(pdfText.slice(doc.map[at], doc.map[at + needle.length - 1] + 1)).toBe('FOA Number: PA-23-152')
    }
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
