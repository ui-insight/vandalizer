import { useId, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, Download, Expand, FileText, Globe2, LockKeyhole, Share2, X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { artifactContentUrl } from '../../api/artifacts'

export function PageDialog({ title, children, onClose, wide = false, busy = false }: {
  title: string; children: ReactNode; onClose: () => void; wide?: boolean; busy?: boolean
}) {
  const id = useId()
  return createPortal(<div className="page-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, fallbackFocus: () => document.getElementById(id)!, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
      <section className={`page-dialog${wide ? ' page-dialog-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={id} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!busy) onClose() } }}>
        <header className="page-dialog-header"><h2 id={id} tabIndex={-1}>{title}</h2><button className="page-icon-button" type="button" aria-label={`Close ${title}`} disabled={busy} onClick={onClose}><X size={20} /></button></header>
        <div className="page-dialog-body">{children}</div>
      </section>
    </FocusTrap>
  </div>, document.body)
}

export function PageBadge({ published = false, children }: { published?: boolean; children: ReactNode }) {
  const Icon = published ? Globe2 : LockKeyhole
  return <span className={`page-badge${published ? ' page-badge-public' : ''}`}><Icon size={13} aria-hidden="true" />{children}</span>
}

export function PagePreview({ src, html, title, compact = false, thumbnail = false }: {
  src?: string; html?: string; title: string; compact?: boolean; thumbnail?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  if (thumbnail) return <div className="page-thumbnail" aria-hidden="true"><iframe src={src} title={`${title} thumbnail`} sandbox="" referrerPolicy="no-referrer" loading="lazy" tabIndex={-1} /></div>
  const frame = (large: boolean) => <iframe src={src} srcDoc={html} title={large ? `${title} expanded preview` : 'Page preview'} sandbox="" referrerPolicy="no-referrer" className={large ? 'page-preview-expanded' : 'page-preview-frame'} />
  return <div className={`page-preview${compact ? ' page-preview-compact' : ''}`}>
    <div className="page-preview-bar"><span><FileText size={14} aria-hidden="true" />{compact ? 'Page preview' : 'Preview'}</span><button type="button" className="page-text-button" onClick={() => setExpanded(true)}><Expand size={15} aria-hidden="true" />Expand preview</button></div>
    {frame(false)}
    {expanded && <PageDialog title={title} wide onClose={() => setExpanded(false)}>{frame(true)}</PageDialog>}
  </div>
}

export function PageActions({ uuid, revision, title, share = true }: { uuid: string; revision: string; title: string; share?: boolean }) {
  const href = `/pages/${encodeURIComponent(uuid)}`
  return <div className="page-actions">
    <a className="page-button page-button-primary" aria-label={`Open page: ${title}`} href={href} target="_blank" rel="noreferrer"><ArrowUpRight size={16} aria-hidden="true" />Open page</a>
    <a className="page-button" aria-label={`Download HTML: ${title}`} href={`${artifactContentUrl(uuid, revision)}?download=true`}><Download size={16} aria-hidden="true" />Download HTML</a>
    {share && <a className="page-button" aria-label={`Share: ${title}`} href={`${href}#share`} target="_blank" rel="noreferrer"><Share2 size={16} aria-hidden="true" />Share</a>}
  </div>
}

export function pagesUrl(projectUuid?: string) {
  return `/?mode=files&files=pages${projectUuid ? `&project=${encodeURIComponent(projectUuid)}` : ''}`
}
