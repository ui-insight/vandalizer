import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react'
import { createPortal } from 'react-dom'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { X } from 'lucide-react'
import { formatPageLocator } from '../../utils/pageLocator'
import type { WorkflowCitation } from '../../types/workflow'

/**
 * Markdown output with knowledge-base citations rendered inline.
 *
 * A grounded task is told to cite the source line shown above each passage,
 * e.g. `[OMB Uniform Guidance — Subpart F · p. 12]`, and the run keeps every
 * passage it retrieved (`retrieved_sources`, each with that `label` and its
 * `content`). Here each bracketed citation that matches a retrieved passage
 * becomes a chip beside the claim; clicking it opens a popover with the
 * passage text, so a reader can check the claim against what it rests on.
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
  //    names a page, a passage that covers it.
  const page = citedPage(t)
  const titleOnly = t.replace(/\s*·?\s*p\. \d+(\s*-\s*\d+)?\s*$/, '').trim()
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
 *  appear as "§ 200.403" (or "200.403" followed by a heading) in the passage. */
export function matchSectionReference(section: string, sources: WorkflowCitation[]): number | null {
  const wanted = section.trim()
  if (!/^\d{2,4}\.\d{1,4}$/.test(wanted)) return null
  const escaped = wanted.replace('.', '\\.')
  // "§ 200.407 Prior written approval." — the marker followed by a heading is
  // the section itself; "(see § 200.407)" is a passage that merely cites it.
  const heading = new RegExp(`§\\s*${escaped}\\s+[A-Z][a-z]`)
  const mention = new RegExp(`(?:§\\s*|\\b)${escaped}(?![\\d])`)
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

function shortLabel(c: WorkflowCitation): string {
  const locator = formatPageLocator(c.page, c.page_approximate, c.page_end) ?? (c.sheet || null)
  return locator ? `${c.document_title} · ${locator}` : c.document_title
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

  const makeChip = (idx: number, compact: boolean): HTMLElement => {
    const c = sources[idx]
    const chip = doc.createElement('button')
    chip.setAttribute('type', 'button')
    chip.className = compact ? 'kb-cite kb-cite-ref' : 'kb-cite'
    chip.setAttribute('data-cite', String(idx))
    chip.setAttribute('title', `${citationLabel(c)} — click to see the passage`)
    chip.setAttribute('aria-label', `Citation: ${citationLabel(c)}`)
    const n = doc.createElement('span')
    n.className = 'kb-cite-n'
    n.textContent = String(idx + 1)
    chip.appendChild(n)
    if (!compact) chip.appendChild(doc.createTextNode(shortLabel(c)))
    return chip
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
      const idx = matchSectionReference(m[1], sources)
      if (idx === null) continue
      spans.push({ start, end, chips: [makeChip(idx, true)], keep: true })
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

/** Markdown → sanitized HTML with citation chips. */
export function renderCitedMarkdown(markdown: string, sources: WorkflowCitation[]): string {
  const html = DOMPurify.sanitize(marked.parse(markdown) as string)
  try {
    return injectCitationChips(html, sources)
  } catch {
    return html
  }
}

// --- Popover ----------------------------------------------------------------

export interface CitationAnchor {
  index: number
  rect: { top: number; bottom: number; left: number; right: number }
}

const POPOVER_WIDTH = 440

/** The passage a citation rests on, floated beside the chip that was clicked. */
export function CitationPopover({ citation, anchor, onClose }: {
  citation: WorkflowCitation
  anchor: CitationAnchor
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node | null
      if (ref.current && target && !ref.current.contains(target)) {
        // A click on another chip is handled by that chip; anything else closes.
        if (!(target instanceof Element) || !target.closest('.kb-cite, .kb-cite-chip')) onClose()
      }
    }
    const onScroll = () => onClose()
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [onClose])

  useEffect(() => { ref.current?.focus() }, [])

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1024
  const vh = typeof window !== 'undefined' ? window.innerHeight : 768
  const width = Math.min(POPOVER_WIDTH, vw - 16)
  const left = Math.max(8, Math.min(anchor.rect.left, vw - width - 8))
  const below = anchor.rect.bottom + 6
  const openAbove = below + 260 > vh && anchor.rect.top > vh / 2
  const style: CSSProperties = {
    position: 'fixed', left, width, zIndex: 3000,
    ...(openAbove ? { bottom: vh - anchor.rect.top + 6 } : { top: below }),
    backgroundColor: '#fff', border: '1px solid #d1d5db', borderRadius: 8,
    boxShadow: '0 10px 30px rgba(0,0,0,0.14)', padding: '10px 12px 12px',
    fontFamily: 'inherit', color: '#374151', outline: 'none',
  }
  const locator = formatPageLocator(citation.page, citation.page_approximate, citation.page_end) ?? (citation.sheet || null)
  const relevance = typeof citation.similarity === 'number' ? `${Math.round(citation.similarity * 100)}% match` : null
  const passage = (citation.content || citation.content_preview || '').trim()

  return createPortal(
    <div ref={ref} role="dialog" aria-label={`Passage: ${citationLabel(citation)}`} tabIndex={-1} style={style}>
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
          onClick={onClose}
          aria-label="Close passage"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex', flexShrink: 0 }}
        >
          <X style={{ width: 14, height: 14 }} />
        </button>
      </div>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 4 }}>
        Passage the claim rests on
      </div>
      <div style={{
        fontSize: 12.5, lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        maxHeight: 260, overflowY: 'auto', backgroundColor: '#f9fafb',
        border: '1px solid #e5e7eb', borderRadius: 6, padding: '8px 10px',
      }}>
        {passage || 'The passage text was not stored with this run.'}
      </div>
    </div>,
    document.body,
  )
}

/** Popover state shared by the inline chips and the bottom Sources panel. */
export function useCitationPopover(sources: WorkflowCitation[]) {
  const [anchor, setAnchor] = useState<CitationAnchor | null>(null)
  const close = useCallback(() => setAnchor(null), [])
  const openAt = useCallback((index: number, el: Element) => {
    const r = el.getBoundingClientRect()
    setAnchor(prev => (
      prev && prev.index === index ? null : { index, rect: { top: r.top, bottom: r.bottom, left: r.left, right: r.right } }
    ))
  }, [])
  const citation = anchor ? sources[anchor.index] : undefined
  const popover = anchor && citation
    ? <CitationPopover citation={citation} anchor={anchor} onClose={close} />
    : null
  return { anchor, openAt, close, popover }
}

// --- Component --------------------------------------------------------------

export const CITATION_CHIP_CSS = `
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
`

/**
 * Renders `markdown` with inline citation chips for `sources`, and the
 * popover for whichever chip is open. Click handling is delegated from the
 * container, since the chips live in injected HTML.
 */
export function CitedMarkdown({ markdown, sources, className, style }: {
  markdown: string
  sources: WorkflowCitation[]
  className?: string
  style?: CSSProperties
}) {
  const html = useMemo(() => renderCitedMarkdown(markdown, sources), [markdown, sources])
  const { openAt, popover } = useCitationPopover(sources)

  const onClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    const target = e.target as Element | null
    const chip = target?.closest?.('.kb-cite') as HTMLElement | null
    if (!chip) return
    const idx = parseInt(chip.getAttribute('data-cite') || '', 10)
    if (!Number.isFinite(idx) || !sources[idx]) return
    e.preventDefault()
    e.stopPropagation()
    openAt(idx, chip)
  }

  return (
    <>
      <style>{CITATION_CHIP_CSS}</style>
      <div className={className} style={style} onClick={onClick} dangerouslySetInnerHTML={{ __html: html }} />
      {popover}
    </>
  )
}
