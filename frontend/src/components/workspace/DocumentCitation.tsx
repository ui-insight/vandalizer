import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { FileText, X } from 'lucide-react'
import { fieldSupportState, type ExtractionFieldSource } from '../../api/extractions'
import { useOptionalWorkspace } from '../../contexts/WorkspaceContext'
import { formatPageLocator } from '../../utils/pageLocator'
import {
  CAPTION_STYLE, FloatingCard, MarkedText, PASSAGE_BOX_STYLE, floatAnchorOf, loosePattern, type FloatAnchor,
} from './CitedMarkdown'

/**
 * A chip that ties a value in a workflow's output to the place in an uploaded
 * document it was traced to — the document-side twin of the knowledge-base
 * chip in CitedMarkdown. Clicking it shows the document's own text at that
 * place with the value marked, and opens the document there.
 *
 * Only places the engine located in the document's text get a chip: an
 * Extraction field whose quoted passage was found and holds the value
 * (`support == "supported"`), or a Form Filler value found by searching the
 * inputs. The page comes from the document's page markers, never from a
 * model, and an estimated page (a scan) says so.
 */

export interface DocumentCitation {
  documentUuid: string
  documentTitle: string
  page: number | null
  pageApproximate: boolean
  /** The document's text at the traced place, as the check found it. */
  excerpt: string
  /** The value the excerpt was checked for, marked inside it. */
  value: string
  /** What the engine checked. `passage`: the model quoted this passage, it
   *  was found in the document and the value is in it (Extraction).
   *  `search`: the value itself was searched for, and this is where it first
   *  appears (Form Filler). */
  check: 'passage' | 'search'
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try { return JSON.stringify(value) } catch { return String(value) }
}

/** The chip for an Extraction field's traced source, or null unless the
 *  check found the value inside a passage located in a document. */
export function citationFromFieldSource(src: ExtractionFieldSource | null | undefined, value: unknown): DocumentCitation | null {
  if (!src || fieldSupportState(src) !== 'supported') return null
  const excerpt = (src.quote || '').trim()
  if (!src.document_uuid || !excerpt) return null
  return {
    documentUuid: src.document_uuid,
    documentTitle: src.document_title || 'Document',
    page: typeof src.page === 'number' ? src.page : null,
    pageApproximate: src.page_approximate === true,
    excerpt,
    value: valueText(value),
    check: 'passage',
  }
}

/** The chip for a Form Filler value, or null unless it was found in a
 *  document (a value found in the previous step's output has no document). */
export function citationFromFillReport(f: {
  status: string
  value?: unknown
  document_uuid?: string | null
  document_title?: string | null
  page?: number | null
  page_approximate?: boolean
  quote?: string
}): DocumentCitation | null {
  if (f.status !== 'supported' || !f.document_uuid) return null
  // The report keeps 60 characters either side of the value and marks a cut
  // with "…"; the ellipses are not document text.
  const excerpt = (f.quote || '').replace(/^…\s*/, '').replace(/\s*…$/, '').trim()
  if (!excerpt) return null
  return {
    documentUuid: f.document_uuid,
    documentTitle: f.document_title || 'Document',
    page: typeof f.page === 'number' ? f.page : null,
    pageApproximate: f.page_approximate === true,
    excerpt,
    value: valueText(f.value),
    check: 'search',
  }
}

/** "Award notice.pdf · p. 2" — what the chip says. */
export function documentCitationLabel(c: DocumentCitation): string {
  const locator = formatPageLocator(c.page, c.pageApproximate)
  return locator ? `${c.documentTitle} · ${locator}` : c.documentTitle
}

/** Where the value sits in the excerpt: of its occurrences, the one nearest
 *  the middle — a Form Filler excerpt is cut around the value, and a short
 *  value ("2") can occur elsewhere in it too. Null when it is not there as
 *  written (the check matched "1240" to "$1,240.00" as the same number). */
export function valueRangeIn(excerpt: string, value: string): [number, number] | null {
  const v = value.trim()
  if (!v) return null
  const re = new RegExp(loosePattern(v), 'gi')
  const middle = excerpt.length / 2
  let best: [number, number] | null = null
  for (const m of excerpt.matchAll(re)) {
    const start = m.index ?? 0
    const end = start + m[0].length
    // A whole value, not a slice of a longer word or number.
    if (/[\p{L}\p{N}]/u.test(excerpt[start - 1] ?? '') && /[\p{L}\p{N}]/u.test(v[0])) continue
    if (/[\p{L}\p{N}]/u.test(excerpt[end] ?? '') && /[\p{L}\p{N}]/u.test(v[v.length - 1])) continue
    if (!best || Math.abs(start - middle) < Math.abs(best[0] - middle)) best = [start, end]
  }
  return best
}

const CHECK_CAPTION: Record<DocumentCitation['check'], string> = {
  passage: 'Passage the value was extracted from — found in the document, and it contains the value',
  search: 'Where this value appears in the document — the first place a search found it',
}

/** The excerpt behind a document chip, floated beside it, with a way into
 *  the document at that page. */
function DocumentCitationPopover({ citation, anchor, onClose, onOpen }: {
  citation: DocumentCitation
  anchor: FloatAnchor
  onClose: () => void
  onOpen: (() => void) | null
}) {
  const boxRef = useRef<HTMLDivElement>(null)
  const markRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const box = boxRef.current, mark = markRef.current
    if (box && mark) box.scrollTop = Math.max(0, mark.offsetTop - 24)
  }, [])

  const locator = formatPageLocator(citation.page, citation.pageApproximate)
  const range = valueRangeIn(citation.excerpt, citation.value)
  return (
    <FloatingCard anchor={anchor} label={`Document source: ${documentCitationLabel(citation)}`} onClose={onClose}>
      {dismiss => (<>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: '#92400e' }}>
              Uploaded document
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: '#111827', lineHeight: 1.3, wordBreak: 'break-word' }}>
              {citation.documentTitle}{locator ? ` · ${locator}` : ''}
            </div>
            {citation.pageApproximate && (
              <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>page estimated from a scan</div>
            )}
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Close document source"
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#6b7280', display: 'flex', flexShrink: 0 }}
          >
            <X style={{ width: 14, height: 14 }} />
          </button>
        </div>
        <div style={CAPTION_STYLE}>{CHECK_CAPTION[citation.check]}</div>
        <div ref={boxRef} style={PASSAGE_BOX_STYLE}>
          <MarkedText text={citation.excerpt} ranges={range ? [range] : []} markRef={markRef} />
        </div>
        {onOpen && (
          <button
            type="button"
            onClick={onOpen}
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

const CHIP_STYLE: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4, maxWidth: 220, height: 20,
  padding: '0 8px 0 5px', fontFamily: 'inherit', fontSize: 11, fontWeight: 500, lineHeight: '18px',
  color: '#92400e', backgroundColor: '#fef3c7', border: '1px solid #fde68a', borderRadius: 999,
  cursor: 'pointer', whiteSpace: 'nowrap', overflow: 'hidden',
}

/** A document chip and its popover. Outside the workspace (a test, a shared
 *  page) the popover still shows the excerpt, without the open button. */
export function DocumentCitationChip({ citation }: { citation: DocumentCitation }) {
  const ws = useOptionalWorkspace()
  const [anchor, setAnchor] = useState<FloatAnchor | null>(null)
  const close = useCallback(() => setAnchor(null), [])
  const label = documentCitationLabel(citation)
  const locator = formatPageLocator(citation.page, citation.pageApproximate)

  const open = ws ? () => {
    setAnchor(null)
    // The file viewer sits in the left panel, which only the files mode
    // shows; the workflow stays open on the right.
    ws.setWorkspaceMode('files')
    ws.viewDocument(citation.documentUuid, citation.documentTitle, {
      terms: [citation.excerpt],
      page: citation.page,
      // The chip says "p. ~N" for a scan: the viewer must not drop the hedge.
      pageApproximate: citation.pageApproximate,
    })
  } : null

  return (
    <>
      <button
        type="button"
        className="doc-cite"
        title={`${label} — click to see where this value is in the document`}
        aria-label={`Document source: ${label}`}
        aria-haspopup="dialog"
        aria-expanded={anchor !== null}
        onClick={e => {
          const el = e.currentTarget
          setAnchor(prev => (prev && prev.el === el ? null : floatAnchorOf(el)))
        }}
        style={CHIP_STYLE}
      >
        <FileText aria-hidden="true" style={{ width: 11, height: 11, flexShrink: 0 }} />
        {/* A long file name gives way; the page is the part that matters. */}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{citation.documentTitle}</span>
        {locator && <span style={{ flexShrink: 0 }}>· {locator}</span>}
      </button>
      {anchor && <DocumentCitationPopover citation={citation} anchor={anchor} onClose={close} onOpen={open} />}
    </>
  )
}
