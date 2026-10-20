import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react'
import { BookOpen, FileText, Loader2, X } from 'lucide-react'
import { useOptionalWorkspace } from '../../contexts/WorkspaceContext'
import type { SourcedStatement, SourcingLink, SourcingTarget, WorkflowSourcing } from '../../types/workflow'
import { formatPageLocator } from '../../utils/pageLocator'
import {
  CAPTION_STYLE, FloatingCard, MarkedText, PASSAGE_BOX_STYLE, SOURCING_CSS, floatAnchorOf,
  type CitedSourcing, type FloatAnchor,
} from './CitedMarkdown'
import { codePointIndex, sourceLabel, statementAttrs, stripFormatting, viewerTerm } from './sourcingSpans'

/**
 * Sourcing in the run view, a step's "Last run output" and Test Step.
 *
 * After a run completes, the backend traces each statement of each output
 * to an input document or a knowledge-base passage (output_sourcing.py) —
 * linked only when a judge says the passage states it and the engine
 * confirms the excerpt word for word, every value in it, the label beside
 * each value, and the page. A traced statement gets a subtle underline;
 * clicking it shows the source text with the supporting words highlighted
 * and, for a document, opens it at that page. Untraced statements stay as
 * written, and a reviewer can tint them.
 */

// --- Popover ----------------------------------------------------------------

function SourcePopover({ link, anchor, onClose }: { link: SourcingLink; anchor: FloatAnchor; onClose: () => void }) {
  const ws = useOptionalWorkspace()
  const boxRef = useRef<HTMLDivElement>(null)
  const markRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const box = boxRef.current, mark = markRef.current
    if (box && mark) box.scrollTop = Math.max(0, mark.offsetTop - 24)
  }, [link])

  const isDoc = link.kind === 'document'
  const locator = formatPageLocator(link.page, link.page_approximate, link.page_end)
  // The excerpt as the page reads, without the marks a text extractor
  // wrote into it (`## <u>Title</u>`, `**`); the quote's offsets, counted
  // in the stored text, are carried over so the same words stay marked.
  const at = codePointIndex(link.excerpt || '')
  const excerpt = link.excerpt ? stripFormatting(link.excerpt) : null
  const range: [number, number] | null = excerpt
    ? [excerpt.at(at(link.quote_start)), excerpt.at(at(link.quote_end))]
    : null
  const title = isDoc ? (link.document_title || 'Document') : (link.document_title || link.label || 'Passage')
  const kicker = isDoc ? 'Uploaded document' : (link.kb_title || 'Knowledge base')

  const open = isDoc && ws && link.document_uuid ? () => {
    onClose()
    // The file viewer sits in the left panel, which only the files mode
    // shows; the workflow stays open on the right.
    ws.setWorkspaceMode('files')
    ws.viewDocument(link.document_uuid as string, link.document_title || 'Document', {
      terms: [viewerTerm(link.quote)],
      page: typeof link.page === 'number' ? link.page : null,
      pageApproximate: link.page_approximate === true,
    })
  } : null

  return (
    <FloatingCard anchor={anchor} label={`Source: ${sourceLabel(link)}`} onClose={onClose}>
      {dismiss => (<>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
              color: isDoc ? '#92400e' : '#0369a1',
            }}>
              {kicker}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: '#111827', lineHeight: 1.3, wordBreak: 'break-word' }}>
              {title}{locator ? ` · ${locator}` : ''}
            </div>
            {link.page_approximate && (
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>page estimated from a scan</div>
            )}
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Close source"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex', flexShrink: 0 }}
          >
            <X style={{ width: 14, height: 14 }} />
          </button>
        </div>
        <div style={CAPTION_STYLE}>Highlighted: the words this statement rests on, found here as written</div>
        <div ref={boxRef} style={PASSAGE_BOX_STYLE}>
          {excerpt
            ? <MarkedText text={excerpt.text} ranges={range ? [range] : []} markRef={markRef} />
            : stripFormatting(link.quote || '').text}
        </div>
        {open && (
          <button
            type="button"
            onClick={open}
            style={{
              marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '4px 10px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              color: '#7c2d12', backgroundColor: '#ffedd5', border: '1px solid #fed7aa',
              borderRadius: 6, cursor: 'pointer',
            }}
          >
            <FileText style={{ width: 13, height: 13 }} />
            {locator ? `Open at ${locator}` : 'Open the document'}
          </button>
        )}
      </>)}
    </FloatingCard>
  )
}

/** Which source is open, beside which statement. */
export function useSourcePopover(sources: SourcingLink[]) {
  const [state, setState] = useState<{ src: number; anchor: FloatAnchor } | null>(null)
  const close = useCallback(() => setState(null), [])
  const open = useCallback((src: number, el: HTMLElement) => {
    setState(prev => (prev && prev.anchor.el === el ? null : { src, anchor: floatAnchorOf(el) }))
  }, [])
  const link = state ? sources[state.src] : undefined
  const popover = state && link ? <SourcePopover link={link} anchor={state.anchor} onClose={close} /> : null
  return { open, popover }
}

// --- Summary ----------------------------------------------------------------

const SUMMARY_STYLE: CSSProperties = {
  display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '4px 12px',
  fontSize: 12, color: '#6b7280', margin: '0 0 8px',
}

/** "41 of 52 statements traced to a source", with the reviewer toggle that
 *  tints the rest; "Tracing sources…" while the trace runs. */
export function SourcingSummary({ sourcing, target, showUntraced, onToggle }: {
  sourcing: WorkflowSourcing | null | undefined
  target: string
  showUntraced: boolean
  onToggle: (v: boolean) => void
}) {
  if (!sourcing) return null
  if (sourcing.status === 'pending' || sourcing.status === 'running') {
    return (
      <div role="status" style={SUMMARY_STYLE}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Loader2 className="animate-spin" style={{ width: 12, height: 12 }} />
          Tracing sources…
        </span>
      </div>
    )
  }
  if (sourcing.status === 'failed') {
    return <div style={SUMMARY_STYLE}>{sourcing.error || 'Sources could not be traced.'}</div>
  }
  const t = sourcing.targets?.[target]
  if (!t || t.summary.statements === 0) return null
  const { statements, traced } = t.summary
  return (
    <div style={SUMMARY_STYLE}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <BookOpen aria-hidden="true" style={{ width: 12, height: 12 }} />
        {traced} of {statements} statement{statements === 1 ? '' : 's'} traced to a source
      </span>
      {traced < statements && (
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer', userSelect: 'none' }}>
          <input type="checkbox" checked={showUntraced} onChange={e => onToggle(e.target.checked)} style={{ margin: 0 }} />
          Highlight untraced
        </label>
      )}
    </div>
  )
}

/** Sourcing for one output (`target`): the summary line, the props that
 *  underline a text output, the popover, and the toggle state. */
export function useSourcing(sourcing: WorkflowSourcing | null | undefined, target: string) {
  const [showUntraced, setShowUntraced] = useState(false)
  const t: SourcingTarget | undefined = sourcing?.status === 'done' ? sourcing.targets?.[target] : undefined
  const sources = useMemo(() => sourcing?.sources ?? [], [sourcing])
  const { open, popover } = useSourcePopover(sources)
  const text: CitedSourcing | undefined = t && t.format === 'text'
    ? { rows: t.statements, sources, showUntraced, onOpen: open }
    : undefined
  const summary = (
    <SourcingSummary sourcing={sourcing} target={target} showUntraced={showUntraced} onToggle={setShowUntraced} />
  )
  return { target: t, sources, showUntraced, open, popover, summary, text }
}

// --- JSON -------------------------------------------------------------------

type Leaf = { i: number; a: number | null; b: number | null }

function pathKey(path: Array<string | number>): string {
  return JSON.stringify(path)
}

/**
 * `value` pretty-printed exactly as `JSON.stringify(value, null, 2)`, with
 * each statement marked inside it. `leafSpan(row)` gives a statement's
 * offsets inside the string at its path (`s`/`e` for a structured output,
 * `ls`/`le` for JSON written as text), or null for a whole leaf.
 */
export function SourcedJson({ value, rows, sources, showUntraced, onOpen, leafSpan, style }: {
  value: unknown
  rows: SourcedStatement[]
  sources: SourcingLink[]
  showUntraced: boolean
  onOpen: (src: number, el: HTMLElement) => void
  leafSpan: (row: SourcedStatement) => [number, number] | null
  style?: CSSProperties
}) {
  const byPath = useMemo(() => {
    const m = new Map<string, Leaf[]>()
    rows.forEach((r, i) => {
      if (!Array.isArray(r.p)) return
      const span = leafSpan(r)
      const list = m.get(pathKey(r.p)) ?? []
      list.push({ i, a: span ? span[0] : null, b: span ? span[1] : null })
      m.set(pathKey(r.p), list)
    })
    return m
  }, [rows, leafSpan])

  const mark = (i: number, text: string, key: string): ReactNode => {
    const attrs = statementAttrs(rows[i], i, sources, showUntraced)
    const traced = attrs.class.startsWith('src-u')
    const src = Number(attrs['data-src'])
    const fire = (el: HTMLElement) => { if (traced && Number.isFinite(src)) onOpen(src, el) }
    return (
      <span
        key={key}
        className={attrs.class}
        title={attrs.title}
        data-stmt={attrs['data-stmt']}
        role={traced ? 'button' : undefined}
        tabIndex={traced ? 0 : undefined}
        onClick={traced ? e => { e.stopPropagation(); fire(e.currentTarget) } : undefined}
        onKeyDown={traced ? (e: KeyboardEvent<HTMLSpanElement>) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fire(e.currentTarget) }
        } : undefined}
      >
        {text}
      </span>
    )
  }

  const nodes = useMemo(() => {
    const out: ReactNode[] = []
    let n = 0
    const k = () => `j${n++}`

    const str = (s: string, path: Array<string | number>) => {
      const leaves = byPath.get(pathKey(path)) ?? []
      const whole = leaves.find(l => l.a === null)
      const at = codePointIndex(s)
      const parts = leaves
        .filter(l => l.a !== null && l.b !== null)
        .map(l => ({ i: l.i, a: at(l.a as number), b: at(l.b as number) }))
        .filter(p => p.b > p.a && p.b <= s.length)
        .sort((x, y) => x.a - y.a)
      const esc = (t: string) => JSON.stringify(t).slice(1, -1)
      if (whole && parts.length === 0) {
        out.push(mark(whole.i, JSON.stringify(s), k()))
        return
      }
      out.push('"')
      let last = 0
      for (const p of parts) {
        if (p.a < last) continue
        if (p.a > last) out.push(esc(s.slice(last, p.a)))
        out.push(mark(p.i, esc(s.slice(p.a, p.b)), k()))
        last = p.b
      }
      if (last < s.length) out.push(esc(s.slice(last)))
      out.push('"')
    }

    const walk = (v: unknown, path: Array<string | number>, indent: string) => {
      if (v === null || v === undefined || typeof v === 'function') {
        out.push('null')
        return
      }
      if (Array.isArray(v)) {
        if (v.length === 0) { out.push('[]'); return }
        const inner = indent + '  '
        out.push('[\n')
        v.forEach((x, idx) => {
          out.push(inner)
          walk(x === undefined || typeof x === 'function' ? null : x, [...path, idx], inner)
          out.push(idx < v.length - 1 ? ',\n' : '\n')
        })
        out.push(indent + ']')
        return
      }
      if (typeof v === 'object') {
        const entries = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== undefined && typeof x !== 'function')
        if (entries.length === 0) { out.push('{}'); return }
        const inner = indent + '  '
        out.push('{\n')
        entries.forEach(([key, x], idx) => {
          out.push(`${inner}${JSON.stringify(key)}: `)
          walk(x, [...path, key], inner)
          out.push(idx < entries.length - 1 ? ',\n' : '\n')
        })
        out.push(indent + '}')
        return
      }
      if (typeof v === 'string') {
        str(v, path)
        return
      }
      const leaf = JSON.stringify(v) ?? 'null'
      const whole = (byPath.get(pathKey(path)) ?? [])[0]
      out.push(whole ? mark(whole.i, leaf, k()) : leaf)
    }

    walk(value, [], '')
    return out
    // `mark` closes over the toggle and sources; both are in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, byPath, sources, showUntraced, onOpen])

  return (
    <>
      <style>{SOURCING_CSS}</style>
      <pre className={showUntraced ? 'show-untraced' : undefined} style={style}>{nodes}</pre>
    </>
  )
}

/** Offsets for a statement of a structured output (`s`/`e`). */
export const structuredLeafSpan = (r: SourcedStatement): [number, number] | null =>
  typeof r.s === 'number' && typeof r.e === 'number' ? [r.s, r.e] : null

/** Offsets for a statement of JSON written as text, shown pretty-printed. */
export const textLeafSpan = (r: SourcedStatement): [number, number] | null =>
  typeof r.ls === 'number' && typeof r.le === 'number' ? [r.ls, r.le] : null
