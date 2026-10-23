import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type ReactNode, type Ref } from 'react'
import { createPortal } from 'react-dom'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { X } from 'lucide-react'
import { formatPageLocator } from '../../utils/pageLocator'
import type { SourcedStatement, SourcingLink, WorkflowCitation } from '../../types/workflow'
import { applySourcingSpans, stripMarks, withSentinels } from './sourcingSpans'

/**
 * Markdown output with knowledge-base citations rendered inline.
 *
 * A grounded task cites a passage by its tag ([KB2]); the engine swaps each
 * tag for the passage's source line, e.g. `[OMB Uniform Guidance — Subpart F
 * · p. 12]`, and the run keeps every passage it retrieved (`retrieved_sources`,
 * each with that `label` and its `content`). A source without pages is told
 * apart by the part of a section a passage is, `· § 200.307 · part 2`, or by
 * its position, `· part 12`. Here each bracketed citation that matches a retrieved passage
 * becomes a chip beside the claim; clicking it opens a popover with the
 * passage text, so a reader can check the claim against what it rests on.
 * A section the task's query named is retrieved whole and cited as such,
 * `· § 200.405`.
 * Bracketed text that matches no passage is left exactly as written — a
 * chip must never point at the wrong passage.
 */

// --- Matching ---------------------------------------------------------------

/** The citation label for a passage: the stored one when the run has it, else
 *  rebuilt the way the backend builds it. */
export function citationLabel(c: WorkflowCitation): string {
  if (c.label) return c.label
  const locator = formatPageLocator(c.page, c.page_approximate, c.page_end) ?? (c.sheet || null)
  const base = locator ? `${c.document_title} · ${locator}` : c.document_title
  return c.kb_title ? `${c.kb_title} — ${base}` : base
}

/** Normalize a citation string so small variations in how the model copies
 *  a label (dash style, "p." vs "page", spacing, a dropped tilde) still match. */
export function normalizeCitation(text: string): string {
  return text
    .toLowerCase()
    .replace(/[‒–—―]/g, '-')
    .replace(/\s*--+\s*/g, ' - ')
    // "·", "•", "|" and "," all separate a source from its page when a
    // model rewrites the label; treat them as one separator.
    .replace(/[·•|,]/g, '·')
    .replace(/\bpages?\s+/g, 'p. ')
    .replace(/\bpp?\.\s*~?\s*/g, 'p. ')
    .replace(/\s*·\s*/g, ' · ')
    .replace(/\s*-\s*/g, ' - ')
    .replace(/[“”"']/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// A section number as normalizeCitation leaves it ("31.205-6" → "31.205 - 6").
const NORM_SECTION = '\\d{1,4}\\.\\d{1,4}(?: - \\d{1,3})?[a-z]?'
// Where a pageless passage sits, at the end of a normalized source line: its
// section ("§ 200.405", "appendix iii"), part of a section ("§ 200.405 ·
// part 2"), or position in the source ("part 12").
const LOCATOR = `(?:(?:§ ?${NORM_SECTION}|(?<=· )appendix [ivxlc]+)(?: · part \\d+)?|\\bpart \\d+)`
const LOCATOR_RE = new RegExp(`${LOCATOR}\\s*$`)
const TRAILING_LOCATOR_RE = new RegExp(`\\s*·?\\s*(?:p\\. \\d+(\\s*-\\s*\\d+)?|${LOCATOR})\\s*$`)

function locatorOf(normalized: string): string | null {
  return LOCATOR_RE.exec(normalized)?.[0].trim().replace(/^§\s*/, '§ ') ?? null
}

function citedPage(normalized: string): number | null {
  const m = /p\. (\d+)/.exec(normalized)
  return m ? parseInt(m[1], 10) : null
}

function coversPage(c: WorkflowCitation, page: number): boolean {
  if (c.page == null) return false
  if (c.page === page) return true
  return c.page_end != null && c.page <= page && page <= c.page_end
}

/** The index of the passage a bracketed citation refers to, or null. */
export function matchCitation(text: string, sources: WorkflowCitation[]): number | null {
  const t = normalizeCitation(text)
  if (t.length < 3) return null
  // 1. The label as the model was shown it.
  for (let i = 0; i < sources.length; i++) {
    if (normalizeCitation(citationLabel(sources[i])) === t) return i
  }
  // 2. The document named (title contained either way) and, when the citation
  //    names a page — or its "part N", the section it is ("§ 200.405"), or
  //    the part of a section ("§ 200.405 · part 2") — the passage that is there.
  const page = citedPage(t)
  const tail = locatorOf(t)
  const titleOnly = t.replace(TRAILING_LOCATOR_RE, '').trim()
  let candidates: number[] = []
  for (let i = 0; i < sources.length; i++) {
    const title = normalizeCitation(sources[i].document_title || '')
    if (title.length < 4) continue
    const kb = normalizeCitation(sources[i].kb_title || '')
    const named = t.includes(title) || (titleOnly.length >= 4 && title.includes(titleOnly))
      || (kb.length >= 4 && titleOnly === kb)
    if (named) candidates.push(i)
  }
  if (page != null) candidates = candidates.filter(i => coversPage(sources[i], page))
  if (tail != null) {
    candidates = candidates.filter(i => locatorOf(normalizeCitation(citationLabel(sources[i]))) === tail)
  }
  if (candidates.length === 0) return null
  // Several tasks can retrieve the same passage; any of them is the same text.
  return candidates[0]
}

const BRACKET_RE = /\[([^[\]\n]{3,300})\]/g

// A regulation section named in the text, e.g. "2 CFR 200.403(h)",
// "§ 200.407", "45 CFR 46.101". A section number is itself a precise
// citation into a regulation base, and a model that keeps a strict JSON
// contract names the section far more reliably than it appends a bracket.
export const SECTION_RE = /(?:§\s*|\b\d{1,2}\s*CFR\s*(?:part\s*)?)?\b(\d{2,4}\.\d{1,4})(?:\([a-z0-9]{1,3}\))*/gi

/** The passage whose text literally contains the section a reference names,
 *  or null. Only a base that holds the regulation qualifies: the marker must
 *  appear as "§ 200.403" (or "200.403" followed by a heading) in the passage.
 *  A bare number in the output ("52.5", "1240.00") may be a figure, not a
 *  section, so with `requireMarker` only a passage that writes "§ 52.5" counts. */
export function matchSectionReference(
  section: string, sources: WorkflowCitation[], { requireMarker = false } = {},
): number | null {
  const wanted = section.trim()
  if (!/^\d{2,4}\.\d{1,4}$/.test(wanted)) return null
  const escaped = wanted.replace('.', '\\.')
  // "§ 200.407 Prior written approval." — the marker followed by a heading is
  // the section itself; "(see § 200.407)" is a passage that merely cites it.
  const heading = new RegExp(`§\\s*${escaped}\\s+[A-Z][a-z]`)
  const mention = new RegExp(`(?:§\\s*${requireMarker ? '' : '|\\b'})${escaped}(?![\\d])`)
  let best: number | null = null
  let bestScore = -Infinity
  for (let i = 0; i < sources.length; i++) {
    const content = sources[i].content || ''
    if (!content) continue
    const h = heading.exec(content)
    const m = h || mention.exec(content)
    if (!m) continue
    // A heading beats a mention; among equals, the earlier the better.
    const score = (h ? 1_000_000 : 0) - m.index
    if (score > bestScore) { best = i; bestScore = score }
  }
  return best
}

/** Skip code, links and anything already a chip. */
const SKIP_TAGS = new Set(['CODE', 'PRE', 'A', 'BUTTON', 'SCRIPT', 'STYLE'])

/** Where in its source a passage sits: the section it is ("§ 200.405", for a
 *  passage retrieved as a whole section), its page(s) or sheet, or — for a
 *  source without pages (a web page, an eCFR subpart) — the part of a
 *  section it is ("§ 200.405 · part 2", "Appendix III · part 4") or its
 *  "part N". */
export function citationLocator(c: WorkflowCitation): string | null {
  const page = formatPageLocator(c.page, c.page_approximate, c.page_end) ?? (c.sheet || null)
  const section = /·\s*((?:§\s*\d{1,4}\.\d{1,4}(?:-\d{1,3})?[a-z]?|Appendix [IVXLC]+)(?:\s*·\s*part \d+)?)\s*$/.exec(c.label || '')?.[1] ?? null
  if (section) return page ? `${section} · ${page}` : section
  if (page) return page
  return /·\s*(part \d+)\s*$/.exec(c.label || '')?.[1] ?? null
}

function shortLabel(c: WorkflowCitation): string {
  const locator = citationLocator(c)
  return locator ? `${c.document_title} · ${locator}` : c.document_title
}

/** A regex source for `needle` compared the way the backend compares text:
 *  case (with the `i` flag), whitespace runs, dash and quote styles aside. */
export function loosePattern(needle: string): string {
  return needle
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s+')
    .replace(/[-‐‑‒–—―]/g, '[-‐‑‒–—―]')
    .replace(/["“”„]/g, '["“”„]')
    .replace(/['‘’]/g, "['‘’]")
}

/** Character ranges in `text` where each of `needles` occurs, matched the way
 *  the backend verified them: case, whitespace, dashes and quotes aside. */
export function findHighlights(text: string, needles: string[]): Array<[number, number]> {
  const ranges: Array<[number, number]> = []
  // A verified excerpt may be several pieces joined by "…"; each is verbatim.
  const pieces = needles.flatMap(n => n.split(/\s*(?:\.\.\.|…)\s*/))
  for (const needle of pieces) {
    const n = needle.trim().replace(/^[;,:]+|[;,:]+$/g, '').trim()
    if (n.length < 3) continue
    const m = new RegExp(loosePattern(n), 'i').exec(text)
    if (m) ranges.push([m.index, m.index + m[0].length])
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged: Array<[number, number]> = []
  for (const r of ranges) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1])
    else merged.push([r[0], r[1]])
  }
  return merged
}

/** The heading line of a section inside a passage ("§ 200.421 Advertising
 *  and public relations."), for a section chip to point at. */
function sectionHeading(text: string, section: string): string | null {
  const escaped = section.replace('.', '\\.')
  const m = new RegExp(`§\\s*${escaped}(?![\\d])[^\\n]{0,120}`).exec(text)
  return m ? m[0] : null
}

/**
 * Replace every bracketed citation in already-sanitized HTML that matches a
 * retrieved passage with a chip. Pure: takes HTML, returns HTML. The chips are
 * built with DOM APIs from the passage data, never from the model's text, so
 * this runs after sanitization without reopening it.
 */
export function injectCitationChips(html: string, sources: WorkflowCitation[]): string {
  // Nothing to link unless there is a bracket or something section-shaped.
  if (!sources.length || !/[[§]|\d\.\d/.test(html)) return html
  const doc = new DOMParser().parseFromString(`<div id="root">${html}</div>`, 'text/html')
  const root = doc.getElementById('root')
  if (!root) return html

  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    let skip = false
    for (let p = n.parentElement; p && p !== root; p = p.parentElement) {
      if (SKIP_TAGS.has(p.tagName)) { skip = true; break }
    }
    if (!skip && n.nodeValue && /[[§]|\d\.\d/.test(n.nodeValue)) textNodes.push(n as Text)
  }

  const makeChip = (idx: number, compact: boolean, section?: string): HTMLElement => {
    const c = sources[idx]
    const chip = doc.createElement('button')
    chip.setAttribute('type', 'button')
    chip.className = compact ? 'kb-cite kb-cite-ref' : 'kb-cite'
    chip.setAttribute('data-cite', String(idx))
    // A section chip points at that section's heading inside the passage.
    if (section) chip.setAttribute('data-section', section)
    chip.setAttribute('title', `${citationLabel(c)} — click to see the passage`)
    chip.setAttribute('aria-label', `Citation: ${citationLabel(c)}`)
    chip.setAttribute('aria-haspopup', 'dialog')
    const n = doc.createElement('span')
    n.className = 'kb-cite-n'
    n.textContent = String(idx + 1)
    chip.appendChild(n)
    if (!compact) chip.appendChild(doc.createTextNode(shortLabel(c)))
    return chip
  }

  // The same section is usually named many times in one output.
  const sectionMatches = new Map<string, number | null>()
  const sectionMatch = (section: string, requireMarker: boolean): number | null => {
    const key = `${section}|${requireMarker}`
    if (!sectionMatches.has(key)) sectionMatches.set(key, matchSectionReference(section, sources, { requireMarker }))
    return sectionMatches.get(key) ?? null
  }

  for (const node of textNodes) {
    const text = node.nodeValue || ''
    // Every replacement in this text node: [start, end, chips, keepText].
    const spans: Array<{ start: number; end: number; chips: HTMLElement[]; keep: boolean }> = []

    BRACKET_RE.lastIndex = 0
    for (let m = BRACKET_RE.exec(text); m; m = BRACKET_RE.exec(text)) {
      // A bracket may hold several citations separated by semicolons.
      const parts = m[1].split(/\s*;\s*/).filter(Boolean)
      const matches = parts.map(p => matchCitation(p, sources))
      if (matches.some(i => i === null)) continue
      spans.push({
        start: m.index, end: m.index + m[0].length,
        chips: matches.map(i => makeChip(i as number, false)), keep: false,
      })
    }
    // Section references stay as written and get a compact numbered chip
    // right after them; one already inside a matched bracket is skipped.
    SECTION_RE.lastIndex = 0
    for (let m = SECTION_RE.exec(text); m; m = SECTION_RE.exec(text)) {
      const start = m.index, end = m.index + m[0].length
      if (spans.some(s => start < s.end && end > s.start)) continue
      // Named with "§" or "CFR" it is a section; bare, it may be a figure.
      const idx = sectionMatch(m[1], m[0].indexOf(m[1]) === 0)
      if (idx === null) continue
      spans.push({ start, end, chips: [makeChip(idx, true, m[1])], keep: true })
    }
    if (spans.length === 0) continue

    spans.sort((a, b) => a.start - b.start)
    const frag = doc.createDocumentFragment()
    let last = 0
    for (const s of spans) {
      if (s.start < last) continue
      if (s.start > last) frag.appendChild(doc.createTextNode(text.slice(last, s.start)))
      if (s.keep) frag.appendChild(doc.createTextNode(text.slice(s.start, s.end)))
      s.chips.forEach((chip, k) => {
        frag.appendChild(chip)
        if (k < s.chips.length - 1) frag.appendChild(doc.createTextNode(' '))
      })
      last = s.end
    }
    if (last < text.length) frag.appendChild(doc.createTextNode(text.slice(last)))
    node.parentNode?.replaceChild(frag, node)
  }
  return root.innerHTML
}

/** The statements of an output and where each was traced (see
 *  sourcingSpans.ts): underlined when traced, tinted on request when not. */
export interface CitedSourcing {
  rows: SourcedStatement[]
  sources: SourcingLink[]
  showUntraced: boolean
  /** A traced statement was clicked: `src` indexes `sources`. */
  onOpen: (src: number, el: HTMLElement) => void
}

/** Markdown → sanitized HTML with citation chips, and the statements
 *  underlined when `sourcing` is given. */
export function renderCitedMarkdown(
  markdown: string, sources: WorkflowCitation[], sourcing?: Pick<CitedSourcing, 'rows' | 'sources' | 'showUntraced'>,
): string {
  const md = sourcing ? withSentinels(markdown, sourcing.rows) : markdown
  return withChips(DOMPurify.sanitize(marked.parse(md) as string), sources, sourcing)
}

/** Plain text (e.g. a JSON fragment) → escaped HTML with citation chips; the
 *  caller keeps its line breaks with `white-space: pre-wrap`. */
export function renderCitedText(
  text: string, sources: WorkflowCitation[], sourcing?: Pick<CitedSourcing, 'rows' | 'sources' | 'showUntraced'>,
): string {
  const holder = document.createElement('div')
  holder.textContent = sourcing ? withSentinels(text, sourcing.rows) : text
  return withChips(holder.innerHTML, sources, sourcing)
}

function withChips(
  html: string, sources: WorkflowCitation[], sourcing?: Pick<CitedSourcing, 'rows' | 'sources' | 'showUntraced'>,
): string {
  try {
    const spanned = sourcing ? applySourcingSpans(html, sourcing.rows, sourcing.sources, sourcing.showUntraced) : html
    // Sanitized again after the parse/serialize round trip, so the HTML React
    // receives is exactly what DOMPurify last approved.
    return DOMPurify.sanitize(injectCitationChips(spanned, sources))
  } catch {
    // Never show a mark: without its spans the text is what was written.
    return sourcing ? stripMarks(html) : html
  }
}

// --- Popover ----------------------------------------------------------------

/** Where a floating card sits: the chip that opened it (focus returns to it on
 *  Escape) and that chip's box on screen. */
export interface FloatAnchor {
  el: Element
  rect: { top: number; bottom: number; left: number; right: number }
}

interface CitationAnchor extends FloatAnchor {
  index: number
  /** Set when a section chip ("2 CFR 200.421") opened it: the heading of that
   *  section in the passage is what gets highlighted. */
  section: string | null
}

const POPOVER_WIDTH = 440

/** The anchor for a chip element, read at the moment it is clicked. */
export function floatAnchorOf(el: Element): FloatAnchor {
  const r = el.getBoundingClientRect()
  return { el, rect: { top: r.top, bottom: r.bottom, left: r.left, right: r.right } }
}

/**
 * A card floated beside the chip that opened it — the knowledge-base passage
 * and the document excerpt both open in one. Escape, and the card's own close
 * button (handed to `children` as `dismiss`), close it and give focus back to
 * the chip; a click or a page scroll anywhere else closes it too.
 */
export function FloatingCard({ anchor, label, onClose, children }: {
  anchor: FloatAnchor
  label: string
  onClose: () => void
  children: (dismiss: () => void) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)

  // Escape and the close button hand focus back to the chip; a click or
  // scroll elsewhere leaves focus wherever the reader put it.
  const dismiss = useCallback(() => {
    onClose()
    if (anchor.el instanceof HTMLElement && anchor.el.isConnected) anchor.el.focus()
  }, [onClose, anchor.el])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') dismiss() }
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node | null
      // The opening chip toggles itself on click; any other click closes,
      // including one on a chip whose own popover then opens.
      if (target && !ref.current?.contains(target) && !anchor.el.contains(target)) onClose()
    }
    // Scrolling the passage inside the popover must not close it.
    const onScroll = (e: Event) => {
      if (!(e.target instanceof Node && ref.current?.contains(e.target))) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [onClose, dismiss, anchor.el])

  useEffect(() => { ref.current?.focus() }, [])

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768
  const width = Math.min(POPOVER_WIDTH, vw - 16)
  const left = Math.max(8, Math.min(anchor.rect.left, vw - width - 8))
  const below = anchor.rect.bottom + 6
  const roomBelow = vh - below - 8
  const roomAbove = anchor.rect.top - 6 - 8

  // Placed by the card's real height, measured before it is painted: below
  // the chip when it fits, else above, else on the roomier side scrolling
  // within it. A guessed height let a source card (taller, with its "Open
  // at p. N" button last) run past the window's edge, where nothing could
  // reach it — scrolling the page closes the card.
  const [fit, setFit] = useState<{ above: boolean; maxHeight?: number } | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const height = el.scrollHeight + (el.offsetHeight - el.clientHeight)
    if (height <= roomBelow) setFit({ above: false })
    else if (height <= roomAbove) setFit({ above: true })
    else if (roomAbove > roomBelow) setFit({ above: true, maxHeight: roomAbove })
    else setFit({ above: false, maxHeight: Math.max(roomBelow, 120) })
  }, [roomBelow, roomAbove])

  const openAbove = fit ? fit.above : below + 260 > vh && anchor.rect.top > vh / 2
  const style: CSSProperties = {
    position: 'fixed', left, width, zIndex: 3000, boxSizing: 'border-box',
    ...(openAbove ? { bottom: vh - anchor.rect.top + 6 } : { top: below }),
    ...(fit?.maxHeight ? { maxHeight: fit.maxHeight, overflowY: 'auto' } : {}),
    backgroundColor: '#fff', border: '1px solid #d1d5db', borderRadius: 8,
    boxShadow: '0 10px 30px rgba(0,0,0,0.14)', padding: '10px 12px 12px',
    fontFamily: 'inherit', color: '#374151', outline: 'none',
  }
  return createPortal(
    <div ref={ref} role="dialog" aria-label={label} tabIndex={-1} style={style}>
      {children(dismiss)}
    </div>,
    document.body,
  )
}

/** `text` with each of `ranges` marked; the first mark takes `markRef`, so
 *  the box around it can scroll it into view. */
export function MarkedText({ text, ranges, markRef }: {
  text: string
  ranges: Array<[number, number]>
  markRef?: Ref<HTMLElement>
}) {
  const segments: Array<{ text: string; mark: boolean }> = []
  let at = 0
  for (const [a, b] of ranges) {
    if (a > at) segments.push({ text: text.slice(at, a), mark: false })
    segments.push({ text: text.slice(a, b), mark: true })
    at = b
  }
  if (at < text.length) segments.push({ text: text.slice(at), mark: false })
  const firstMark = segments.findIndex(seg => seg.mark)
  return (
    <>
      {segments.map((seg, i) => {
        if (!seg.mark) return <span key={i}>{seg.text}</span>
        return (
          <mark key={i} ref={i === firstMark ? markRef : undefined} style={{ backgroundColor: '#fef08a', color: '#111827', padding: '0 1px', borderRadius: 2 }}>
            {seg.text}
          </mark>
        )
      })}
    </>
  )
}

/** The scrolling box a passage or excerpt is shown in. */
export const PASSAGE_BOX_STYLE: CSSProperties = {
  position: 'relative',
  fontSize: 12.5, lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  maxHeight: 260, overflowY: 'auto', backgroundColor: '#f9fafb',
  border: '1px solid #e5e7eb', borderRadius: 6, padding: '8px 10px',
}

/** The small uppercase line above a passage that says what is highlighted. */
export const CAPTION_STYLE: CSSProperties = {
  fontSize: 10.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 4,
}

/** The passage a citation rests on, floated beside the chip that was clicked. */
function CitationPopover({ citation, anchor, onClose }: {
  citation: WorkflowCitation
  anchor: CitationAnchor
  onClose: () => void
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const markRef = useRef<HTMLElement>(null)

  // Bring the highlighted text into view inside the passage box — scrolling
  // the box, never the page (a page scroll closes the popover).
  useEffect(() => {
    const box = boxRef.current, mark = markRef.current
    if (box && mark) box.scrollTop = Math.max(0, mark.offsetTop - 24)
  }, [anchor.index, anchor.section])

  const locator = citationLocator(citation)
  const relevance = typeof citation.similarity === 'number' ? `${Math.round(citation.similarity * 100)}% match` : null
  const passage = (citation.content || citation.content_preview || '').trim()
  // What to highlight: a section chip points at that section's heading; a
  // citation chip at the excerpts the check verified for this passage.
  const heading = anchor.section ? sectionHeading(passage, anchor.section) : null
  const quotes = (citation.quotes || []).map(q => q.quote).filter(Boolean)
  const ranges = findHighlights(passage, heading ? [heading] : quotes)
  const caption = heading
    ? `§ ${anchor.section} in this passage`
    : ranges.length > 0
      ? 'Highlighted: the text the statement rests on, checked against this passage'
      : 'Passage the claim rests on'

  return (
    <FloatingCard anchor={anchor} label={`Passage: ${citationLabel(citation)}`} onClose={onClose}>
      {dismiss => (<>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {citation.kb_title && (
              <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: '#0369a1' }}>
                {citation.kb_title}
              </div>
            )}
            <div style={{ fontSize: 12.5, fontWeight: 600, color: '#111827', lineHeight: 1.3, wordBreak: 'break-word' }}>
              {citation.document_title}{locator ? ` · ${locator}` : ''}
            </div>
            {(relevance || citation.page_approximate) && (
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                {[relevance, citation.page_approximate ? 'page estimated from a scan' : null].filter(Boolean).join(' · ')}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Close passage"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex', flexShrink: 0 }}
          >
            <X style={{ width: 14, height: 14 }} />
          </button>
        </div>
        <div style={CAPTION_STYLE}>
          {caption}
        </div>
        <div ref={boxRef} style={PASSAGE_BOX_STYLE}>
          {passage
            ? <MarkedText text={passage} ranges={ranges} markRef={markRef} />
            : 'The passage text was not stored with this run.'}
        </div>
      </>)}
    </FloatingCard>
  )
}

/** Popover state shared by the inline chips and the bottom Sources panel. */
export function useCitationPopover(sources: WorkflowCitation[]) {
  const [anchor, setAnchor] = useState<CitationAnchor | null>(null)
  const close = useCallback(() => setAnchor(null), [])
  const openAt = useCallback((index: number, el: Element) => {
    setAnchor(prev => (
      prev && prev.el === el ? null : { ...floatAnchorOf(el), index, section: el.getAttribute('data-section') }
    ))
  }, [])
  const citation = anchor ? sources[anchor.index] : undefined
  const popover = anchor && citation
    ? <CitationPopover citation={citation} anchor={anchor} onClose={close} />
    : null
  return { anchor, openAt, popover }
}

// --- Component --------------------------------------------------------------

/** A traced statement's underline (amber for a document, blue for a
 *  knowledge-base passage) and an untraced one's tint, shown only while the
 *  reviewer toggle is on. Solid enough to be noticed on the gray output box
 *  and on white (a 1px line at half opacity went unseen), set below the
 *  text so the output stays the thing being read. */
export const SOURCING_CSS = `
.src-u {
  text-decoration-line: underline; text-decoration-style: solid; text-decoration-thickness: 2px;
  text-decoration-color: rgba(217, 119, 6, 0.85); text-underline-offset: 4px;
  cursor: pointer; border-radius: 2px;
}
.src-u.src-kb { text-decoration-color: rgba(2, 132, 199, 0.85); }
.src-u:hover, .src-u:focus-visible { background-color: rgba(253, 230, 138, 0.55); text-decoration-color: #b45309; outline: none; }
.src-u:focus-visible { box-shadow: 0 0 0 2px rgba(180, 83, 9, 0.45); }
.src-u.src-kb:hover, .src-u.src-kb:focus-visible { background-color: rgba(186, 230, 253, 0.6); text-decoration-color: #0369a1; }
.src-u.src-kb:focus-visible { box-shadow: 0 0 0 2px rgba(3, 105, 161, 0.45); }
.show-untraced .src-x { background-color: rgba(251, 113, 133, 0.16); border-radius: 2px; -webkit-box-decoration-break: clone; box-decoration-break: clone; }
`

const CITATION_CHIP_CSS = `
.kb-cite {
  display: inline-flex; align-items: center; gap: 4px; vertical-align: baseline;
  margin: 0 2px; padding: 0 7px 0 3px; max-width: 280px; height: 18px;
  font: inherit; font-size: 11px; font-weight: 500; line-height: 18px;
  color: #075985; background: #e0f2fe; border: 1px solid #bae6fd; border-radius: 999px;
  cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kb-cite:hover, .kb-cite:focus-visible { background: #bae6fd; border-color: #7dd3fc; outline: none; }
.kb-cite-ref { padding: 0 2px; margin: 0 1px 0 3px; height: 16px; vertical-align: super; font-size: 9px; line-height: 16px; }
.kb-cite-n {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 14px; height: 14px; padding: 0 3px; border-radius: 999px;
  background: #0369a1; color: #fff; font-size: 9.5px; font-weight: 700; line-height: 14px;
}
${SOURCING_CSS}
`

/**
 * Renders `markdown` with inline citation chips for `sources`, and the
 * popover for whichever chip is open. Click handling is delegated from the
 * container, since the chips live in injected HTML.
 */
export function CitedMarkdown({ markdown, sources, format = 'markdown', className, style, sourcing }: {
  markdown: string
  sources: WorkflowCitation[]
  /** `text` keeps the string as written (a JSON fragment, say) instead of
   *  rendering it as Markdown; style it with `white-space: pre-wrap`. */
  format?: 'markdown' | 'text'
  className?: string
  style?: CSSProperties
  /** Where each statement came from: spans of `markdown` as written. */
  sourcing?: CitedSourcing
}) {
  const rows = sourcing?.rows
  const traced = sourcing?.sources
  const showUntraced = sourcing?.showUntraced ?? false
  const html = useMemo(() => {
    const spans = rows && traced ? { rows, sources: traced, showUntraced } : undefined
    return format === 'text' ? renderCitedText(markdown, sources, spans) : renderCitedMarkdown(markdown, sources, spans)
  }, [markdown, sources, format, rows, traced, showUntraced])
  const { openAt, popover } = useCitationPopover(sources)

  // A source is opened by a traced statement's underline; a citation chip
  // inside one keeps opening its own passage.
  const openSource = (target: Element | null): boolean => {
    const el = target?.closest?.('.src-u') as HTMLElement | null
    const src = el ? parseInt(el.getAttribute('data-src') || '', 10) : NaN
    if (!el || !sourcing || !Number.isFinite(src) || !sourcing.sources[src]) return false
    sourcing.onOpen(src, el)
    return true
  }

  const onClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    const target = e.target as Element | null
    const chip = target?.closest?.('.kb-cite') as HTMLElement | null
    if (!chip) {
      if (openSource(target)) {
        e.preventDefault()
        e.stopPropagation()
      }
      return
    }
    const idx = parseInt(chip.getAttribute('data-cite') || '', 10)
    if (!Number.isFinite(idx) || !sources[idx]) return
    e.preventDefault()
    e.stopPropagation()
    openAt(idx, chip)
  }

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    if (openSource(e.target as Element | null)) e.preventDefault()
  }

  const classes = [className, showUntraced ? 'show-untraced' : null].filter(Boolean).join(' ') || undefined
  return (
    <>
      <style>{CITATION_CHIP_CSS}</style>
      <div className={classes} style={style} onClick={onClick} onKeyDown={onKeyDown} dangerouslySetInnerHTML={{ __html: html }} />
      {popover}
    </>
  )
}
