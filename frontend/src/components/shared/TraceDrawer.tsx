import { usePanelEffect } from './usePanelEffect'
import { FocusTrap } from './PanelFocusTrap'
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
  usePanelEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !optimized) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        display: 'flex', justifyContent: 'flex-end',
        backgroundColor: 'rgba(0,0,0,0.55)',
      }}
      onClick={onClose}
    >
      <FocusTrap focusTrapOptions={{ escapeDeactivates: false, allowOutsideClick: true, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
      <div role="dialog" aria-modal="true" aria-label="Question trace"
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(680px, 92vw)', height: '100%',
          backgroundColor: 'var(--workspace-canvas)', borderLeft: '1px solid var(--workspace-border)',
          overflow: 'hidden', overflowWrap: 'anywhere',
          display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)', padding: "var(--workspace-space-12) var(--workspace-space-20)", flexShrink: 0, borderBottom: '1px solid var(--workspace-border)' }}>
          <h3 style={{ margin: 0, fontSize: 'var(--workspace-font-body)', color: 'var(--workspace-text)', flex: 1 }}>
            Trace
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: 'var(--workspace-muted)',
              cursor: 'pointer', padding: 'var(--workspace-space-4)', minWidth: 36, minHeight: 'var(--workspace-control-height)', fontFamily: 'inherit',
            }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div role="region" aria-label="Question trace details" tabIndex={0} style={{ minHeight: 0, overflowY: 'auto', padding: 'var(--workspace-space-20)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-16)' }}>
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
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
              {(optimized.retrieved_sources || []).join(', ')}
            </div>
          </Section>
        )}

        {baseline && baseline.actual_answer && (
          <Section label="Default-config answer" muted>
            <Body body={baseline.actual_answer} muted />
            {baseline.reasoning && (
              <div style={{ marginTop: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
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
      </FocusTrap>
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
      gap: 'var(--workspace-space-8)',
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
  const color = score >= 0.7 ? 'var(--workspace-success)' : score >= 0.4 ? 'var(--workspace-warning)' : 'var(--workspace-danger)'
  return (
    <div style={{
      padding: 'var(--workspace-space-12)', borderRadius: 'var(--workspace-radius-small)',
      backgroundColor: primary ? 'rgba(34, 197, 94, 0.06)' : 'var(--workspace-surface)',
      border: `1px solid ${primary ? 'rgba(34, 197, 94, 0.3)' : 'var(--workspace-border)'}`,
    }}>
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 'var(--workspace-font-page-title)', fontWeight: 700, color, marginTop: 'var(--workspace-space-2)' }}>
        {(score * 100).toFixed(0)}%
      </div>
      {verdict && (
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', marginTop: 'var(--workspace-space-2)' }}>{verdict}</div>
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
        fontSize: 'var(--workspace-font-meta)', color: muted ? 'var(--workspace-muted)' : 'var(--workspace-muted)',
        textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 'var(--workspace-space-4)',
      }}>{label}</div>
      {children}
    </div>
  )
}

function Body({ body, muted = false }: { body: string; muted?: boolean }) {
  return (
    <div style={{
      fontSize: 'var(--workspace-font-meta)', color: muted ? 'var(--workspace-muted)' : 'var(--workspace-text)',
      whiteSpace: 'pre-wrap' as const, lineHeight: 1.5,
      padding: 'var(--workspace-space-12)', borderRadius: 'var(--workspace-radius-small)',
      backgroundColor: 'var(--workspace-canvas)',
      border: '1px solid var(--workspace-border)',
    }}>
      {body}
    </div>
  )
}

function FactList({
  label, items, tone,
}: { label: string; items: string[]; tone: 'warn' | 'bad' }) {
  const color = tone === 'bad' ? 'var(--workspace-danger)' : 'var(--workspace-warning)'
  return (
    <Section label={label}>
      <ul style={{ margin: 0, paddingLeft: 'var(--workspace-space-20)', color, fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5 }}>
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </Section>
  )
}
