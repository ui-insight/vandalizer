import { useEffect } from 'react'
import { X } from 'lucide-react'
import type { PerQueryResult } from '../../api/knowledge'

interface Props {
  open: boolean
  onClose: () => void
  /** The optimized-config row for the query under inspection. */
  optimized: PerQueryResult | null
  /** The default-config baseline row for the same query (if available). */
  baseline?: PerQueryResult | null
  /** The no-KB baseline row for the same query (optional). */
  noKb?: PerQueryResult | null
}

/**
 * Trace replay drawer — Braintrust's signature feature.
 *
 * Click any per-query cell to see exactly what the optimizer generated and
 * what the judge said about it: query, expected vs actual, retrieved sources,
 * judge verdict + reasoning, missing/hallucinated facts. Without this, every
 * aggregate score is a "trust me" claim.
 */
export function TraceDrawer({ open, onClose, optimized, baseline, noKb }: Props) {
  // Close on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !optimized) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 80,
        display: 'flex', justifyContent: 'flex-end',
        backgroundColor: 'rgba(0,0,0,0.55)',
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(680px, 92vw)', height: '100%',
          backgroundColor: '#161616', borderLeft: '1px solid #2e2e2e',
          padding: 20, overflowY: 'auto',
          display: 'flex', flexDirection: 'column', gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14, color: '#fff', flex: 1 }}>
            Trace
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: '#888',
              cursor: 'pointer', padding: 4, fontFamily: 'inherit',
            }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <Section label="Query">
          <Body body={optimized.query} />
        </Section>

        <ScoreRow optimized={optimized} baseline={baseline} noKb={noKb} />

        <Section label="Optimized config answer">
          <Body body={optimized.actual_answer || '(empty)'} />
        </Section>

        {optimized.reasoning && (
          <Section label="Judge reasoning (optimized)" muted>
            <Body body={optimized.reasoning} muted />
          </Section>
        )}

        {(optimized.missing_facts?.length ?? 0) > 0 && (
          <FactList label="Missing facts" tone="warn" items={optimized.missing_facts || []} />
        )}
        {(optimized.hallucinated_facts?.length ?? 0) > 0 && (
          <FactList label="Hallucinated facts" tone="bad" items={optimized.hallucinated_facts || []} />
        )}

        {(optimized.retrieved_sources?.length ?? 0) > 0 && (
          <Section label="Retrieved sources">
            <div style={{ fontSize: 11, color: '#888' }}>
              {(optimized.retrieved_sources || []).join(', ')}
            </div>
          </Section>
        )}

        {baseline && baseline.actual_answer && (
          <Section label="Default-config answer" muted>
            <Body body={baseline.actual_answer} muted />
            {baseline.reasoning && (
              <div style={{ marginTop: 6, fontSize: 11, color: '#777' }}>
                <em>Judge:</em> {baseline.reasoning}
              </div>
            )}
          </Section>
        )}

        {noKb && noKb.actual_answer && (
          <Section label="No-KB answer (LLM only)" muted>
            <Body body={noKb.actual_answer} muted />
          </Section>
        )}
      </div>
    </div>
  )
}

function ScoreRow({
  optimized, baseline, noKb,
}: { optimized: PerQueryResult; baseline?: PerQueryResult | null; noKb?: PerQueryResult | null }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
      gap: 8,
    }}>
      <ScoreCell label="Optimized" score={optimized.score} verdict={optimized.verdict} primary />
      {baseline && <ScoreCell label="Default" score={baseline.score} verdict={baseline.verdict} />}
      {noKb && <ScoreCell label="No KB" score={noKb.score} verdict={noKb.verdict} />}
    </div>
  )
}

function ScoreCell({
  label, score, verdict, primary = false,
}: { label: string; score: number; verdict?: string | null; primary?: boolean }) {
  const color = score >= 0.7 ? '#22c55e' : score >= 0.4 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{
      padding: 10, borderRadius: 6,
      backgroundColor: primary ? 'rgba(34, 197, 94, 0.06)' : '#1f1f1f',
      border: `1px solid ${primary ? 'rgba(34, 197, 94, 0.3)' : '#2e2e2e'}`,
    }}>
      <div style={{ fontSize: 9, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color, marginTop: 2 }}>
        {(score * 100).toFixed(0)}%
      </div>
      {verdict && (
        <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>{verdict}</div>
      )}
    </div>
  )
}

function Section({ label, muted = false, children }: {
  label: string; muted?: boolean; children: React.ReactNode
}) {
  return (
    <div>
      <div style={{
        fontSize: 10, color: muted ? '#666' : '#888',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4,
      }}>{label}</div>
      {children}
    </div>
  )
}

function Body({ body, muted = false }: { body: string; muted?: boolean }) {
  return (
    <div style={{
      fontSize: 12, color: muted ? '#999' : '#e5e5e5',
      whiteSpace: 'pre-wrap' as const, lineHeight: 1.5,
      padding: 10, borderRadius: 6,
      backgroundColor: '#1a1a1a',
      border: '1px solid #2a2a2a',
    }}>
      {body}
    </div>
  )
}

function FactList({
  label, items, tone,
}: { label: string; items: string[]; tone: 'warn' | 'bad' }) {
  const color = tone === 'bad' ? '#fca5a5' : '#fbbf24'
  return (
    <Section label={label}>
      <ul style={{ margin: 0, paddingLeft: 18, color, fontSize: 12, lineHeight: 1.5 }}>
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </Section>
  )
}
