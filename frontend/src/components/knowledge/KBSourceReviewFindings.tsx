import { ShieldAlert } from 'lucide-react'
import type { KnowledgeBaseSource } from '../../types/knowledge'

const SHOWN = 3

/** What a held web page was held for, with the choice to add it anyway.
 *
 *  A "held" source has nothing indexed yet; a "ready" one had a refresh held
 *  and still answers from its previous text, so the wording differs. The
 *  excerpts are the point: the user decides from the text itself, not from
 *  the detector's label. */
export function KBSourceReviewFindings({
  source, canManage, busy, onAccept, onRemove,
}: {
  source: KnowledgeBaseSource
  canManage: boolean
  busy?: boolean
  onAccept: () => void
  onRemove: () => void
}) {
  const findings = source.review_findings ?? []
  if (findings.length === 0) return null
  const isRefresh = source.status !== 'held'
  const stop = (e: React.MouseEvent) => e.stopPropagation()
  const linkStyle: React.CSSProperties = {
    padding: 0, background: 'transparent', border: 'none',
    fontSize: 11, fontFamily: 'inherit', fontWeight: 600,
    color: '#7aa2f7', textDecoration: 'underline', cursor: busy ? 'default' : 'pointer',
  }
  return (
    <div
      role="alert"
      onClick={stop}
      style={{
        marginTop: 4, padding: '6px 8px', borderRadius: 4,
        border: '1px solid #78350f', backgroundColor: '#2b2113',
        fontSize: 11, color: '#fbbf24', cursor: 'default',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
        <ShieldAlert size={12} style={{ flexShrink: 0 }} />
        {isRefresh
          ? 'A refresh was held — this source still answers from its previous text.'
          : 'Held for review — not added to this knowledge base.'}
      </div>
      <div style={{ color: '#d6c9a8', marginTop: 3 }}>
        Text a reader of the page can’t see, or text written to an AI, changes
        the answers this knowledge base gives everyone. Check what was found:
      </div>
      <ul style={{ margin: '4px 0 0', paddingLeft: 16, color: '#e5e5e5' }}>
        {findings.slice(0, SHOWN).map((f, i) => (
          <li key={i} style={{ marginTop: 2 }}>
            <span style={{ color: '#fbbf24' }}>{f.reason[0].toUpperCase() + f.reason.slice(1)}:</span>{' '}
            <q style={{ fontStyle: 'italic', wordBreak: 'break-word' }}>{f.excerpt}</q>
          </li>
        ))}
      </ul>
      {findings.length > SHOWN && (
        <div style={{ color: '#9a9a9a', marginTop: 2 }}>
          and {findings.length - SHOWN} more — open the source to read the full text.
        </div>
      )}
      {canManage && (
        <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
          <button type="button" disabled={busy} onClick={(e) => { stop(e); onAccept() }} style={linkStyle}
            title="Index this page as it is now. Only text you have not seen here would hold it again.">
            {isRefresh ? 'Accept the new version' : 'Add anyway'}
          </button>
          {!isRefresh && (
            <button type="button" disabled={busy} onClick={(e) => { stop(e); onRemove() }} style={linkStyle}>
              Remove
            </button>
          )}
        </div>
      )}
    </div>
  )
}
