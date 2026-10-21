import type { SourcedStatement, SourcingLink } from '../../types/workflow'
import { formatPageLocator } from '../../utils/pageLocator'

/**
 * Where each statement of an output sits in the rendered HTML.
 *
 * The backend gives every statement as a span of the raw output (Markdown,
 * or JSON written as text). Rendering moves text around — `**` and `|` go,
 * a table cell becomes a <td>, a sentence can run across a <strong> — so a
 * span cannot be found again by searching the HTML for its text (the same
 * sentence can appear twice). Instead a private-use character is put at
 * each span's start and end before Markdown is rendered; it is ordinary
 * text to marked and DOMPurify, so it comes out in the right text node, and
 * each run between a start mark and its end mark becomes a <span>. Nothing
 * in the output's own text changes.
 */

const BASE = 0xe000
const MAX_STATEMENTS = 3000
const MARK_RE = /[-]/
const MARK_RE_ALL = /[-]/g

/** The UTF-16 index of each code-point offset into `text` (the backend
 *  counts code points; an emoji is one there and two here). */
export function codePointIndex(text: string): (cp: number) => number {
  if (!/[\ud800-\udfff]/.test(text)) return cp => Math.max(0, Math.min(cp, text.length))
  const map: number[] = []
  let i = 0
  for (const ch of text) {
    map.push(i)
    i += ch.length
  }
  map.push(i)
  return cp => map[Math.max(0, Math.min(cp, map.length - 1))]
}

/** `text` with a start and an end mark around every statement that has a
 *  span. Overlapping spans are not expected; one that overlaps an earlier
 *  one is left out rather than nested. */
export function withSentinels(text: string, rows: SourcedStatement[]): string {
  const at = codePointIndex(text)
  const spans: Array<{ i: number; a: number; b: number }> = []
  rows.forEach((r, i) => {
    if (i >= MAX_STATEMENTS || typeof r.s !== 'number' || typeof r.e !== 'number' || r.e <= r.s) return
    const a = at(r.s), b = at(r.e)
    if (b <= a || b > text.length) return
    spans.push({ i, a, b })
  })
  spans.sort((x, y) => x.a - y.a)
  let out = ''
  let last = 0
  let lastEnd = -1
  for (const sp of spans) {
    if (sp.a < lastEnd) continue
    out += text.slice(last, sp.a) + String.fromCharCode(BASE + 2 * sp.i) + text.slice(sp.a, sp.b) + String.fromCharCode(BASE + 2 * sp.i + 1)
    last = sp.b
    lastEnd = sp.b
  }
  return out + text.slice(last)
}

// The formatting marks a text extractor (Docling) writes around words, taken
// out one after another: tags such as <u>, runs of `*` and backticks, an
// underscore at a word's edge, a heading's leading `#`s. Group 1, when a
// pattern has one, is the character it looked at, and stays.
const FORMAT_MARKS: RegExp[] = [
  /<\/?[A-Za-z][A-Za-z0-9]{0,10}\s*\/?>/g,
  /[*`]+/g,
  /(^|[^A-Za-z0-9])_+/g,
  /_+(?=[^A-Za-z0-9]|$)/g,
  /^#{1,6}[ \t]+/gm,
]

/** `text` without its formatting marks, line breaks kept, and where each
 *  UTF-16 index of `text` lands in what is left — an index inside a mark
 *  lands where the mark was. */
export function stripFormatting(text: string): { text: string; at: (i: number) => number } {
  let cur = text
  // from[j]: the index in `text` of character j of `cur`.
  let from = Array.from({ length: text.length }, (_, i) => i)
  for (const re of FORMAT_MARKS) {
    let out = ''
    const kept: number[] = []
    let last = 0
    for (const m of cur.matchAll(re)) {
      const a = (m.index ?? 0) + (m[1]?.length ?? 0)
      out += cur.slice(last, a)
      for (let j = last; j < a; j++) kept.push(from[j])
      last = (m.index ?? 0) + m[0].length
    }
    out += cur.slice(last)
    for (let j = last; j < cur.length; j++) kept.push(from[j])
    cur = out
    from = kept
  }
  // before[i]: how many kept characters come before index i of `text`.
  const before: number[] = []
  let k = 0
  for (let i = 0; i <= text.length; i++) {
    while (k < from.length && from[k] < i) k++
    before.push(k)
  }
  return { text: cur, at: i => before[Math.max(0, Math.min(i, text.length))] }
}

/** A quote as the page itself shows it, for the document viewer to find:
 *  the formatting marks a text extractor writes around words (`**`, `<u>`)
 *  are in the stored text but not in the PDF's text layer. */
export function viewerTerm(quote: string): string {
  return stripFormatting(quote).text.replace(/\s+/g, ' ').trim()
}

/** "NoA.pdf · p. 2", or the knowledge-base passage's source line. */
export function sourceLabel(link: SourcingLink): string {
  const locator = formatPageLocator(link.page, link.page_approximate, link.page_end)
  if (link.kind === 'kb') {
    const name = link.label || [link.kb_title, link.document_title].filter(Boolean).join(' — ') || 'Knowledge base passage'
    return locator && !name.includes(locator) ? `${name} · ${locator}` : name
  }
  const name = link.document_title || 'Document'
  return locator ? `${name} · ${locator}` : name
}

const UNTRACED_WHY: Record<string, string> = {
  absent: 'Says the source does not give this — there is no passage to show',
  verdict: 'A judgment drawn from the facts — not something a source states',
}

/** Attributes of the element that marks statement `i`: an underline that
 *  opens its source, or (untraced) a tint the reviewer toggle shows. */
export function statementAttrs(
  row: SourcedStatement, i: number, sources: SourcingLink[], showUntraced: boolean,
): Record<string, string> {
  const link = typeof row.src === 'number' ? sources[row.src] : undefined
  if (link) {
    return {
      class: link.kind === 'kb' ? 'src-u src-kb' : 'src-u',
      'data-stmt': String(i),
      'data-src': String(row.src),
      role: 'button',
      tabindex: '0',
      title: `Source: ${sourceLabel(link)} — click to see where this comes from`,
    }
  }
  // Still being checked: neither underlined nor counted as untraced yet.
  if (row.w) return showUntraced ? { class: 'src-w', title: 'Still being checked' } : { class: 'src-w' }
  const attrs: Record<string, string> = { class: 'src-x' }
  if (showUntraced) attrs.title = UNTRACED_WHY[row.t ?? ''] ?? 'Not traced to a source'
  return attrs
}

/** Turn the marks in `root`'s text into one <span> per run of each
 *  statement's text, then drop any mark left over (one that landed in an
 *  attribute, say). */
export function marksToSpans(root: Element, rows: SourcedStatement[], sources: SourcingLink[], showUntraced: boolean): void {
  const doc = root.ownerDocument
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n as Text)

  let open: number | null = null
  for (const node of nodes) {
    const text = node.nodeValue || ''
    if (open === null && !MARK_RE.test(text)) continue
    const frag = doc.createDocumentFragment()
    let buf = ''
    const flush = () => {
      if (!buf) return
      if (open !== null && rows[open] && buf.trim()) {
        const span = doc.createElement('span')
        for (const [k, v] of Object.entries(statementAttrs(rows[open], open, sources, showUntraced))) span.setAttribute(k, v)
        span.textContent = buf
        frag.appendChild(span)
      } else {
        frag.appendChild(doc.createTextNode(buf))
      }
      buf = ''
    }
    for (const ch of text) {
      const code = ch.charCodeAt(0)
      if (ch.length === 1 && code >= BASE && code < BASE + 2 * MAX_STATEMENTS) {
        flush()
        const idx = (code - BASE) >> 1
        if ((code - BASE) % 2 === 0) open = idx
        else if (open === idx) open = null
        continue
      }
      buf += ch
    }
    flush()
    node.parentNode?.replaceChild(frag, node)
  }
  // A mark can land inside an attribute: a statement that ends on a bare
  // URL makes it part of the autolink's href (percent-encoded there).
  for (const el of Array.from(root.querySelectorAll('*'))) {
    for (const attr of Array.from(el.attributes)) {
      const clean = attr.value.replace(MARK_RE_ALL, '').replace(ENCODED_MARK_RE, '')
      if (clean !== attr.value) el.setAttribute(attr.name, clean)
    }
  }
}

// U+E000–U+F77F in UTF-8, percent-encoded: EE 80–BF xx, EF 80–9D xx.
const ENCODED_MARK_RE = /%EE%[89AB][0-9A-F]%[89AB][0-9A-F]|%EF%(?:8[0-9A-F]|9[0-9A-D])%[89AB][0-9A-F]/gi

/** Already-sanitized HTML (rendered from text with marks) → HTML with the
 *  statements wrapped. Pure: HTML in, HTML out. */
export function applySourcingSpans(html: string, rows: SourcedStatement[], sources: SourcingLink[], showUntraced: boolean): string {
  if (!MARK_RE.test(html)) return html
  const doc = new DOMParser().parseFromString(`<div id="root">${html}</div>`, 'text/html')
  const root = doc.getElementById('root')
  if (!root) return html.replace(MARK_RE_ALL, '')
  marksToSpans(root, rows, sources, showUntraced)
  return root.innerHTML.replace(MARK_RE_ALL, '')
}

/** `text` without marks, for a caller that must never show one. */
export function stripMarks(text: string): string {
  return text.replace(MARK_RE_ALL, '')
}
