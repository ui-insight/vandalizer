import { useEffect, useState } from 'react'
import { Loader2, Inbox, Sparkles, ArrowRight, CheckCircle2 } from 'lucide-react'
import { getOptimizerInbox, type OptimizerInboxItem, type OptimizerInboxResponse } from '../../api/optimizerInbox'

/**
 * Optimizer Inbox  - Phase 6 unified candidate review surface.
 *
 * Shows shadow optimizer runs across KB/extraction/workflow that the
 * system enqueued in response to quality alerts (Phase 6) or report-only
 * signals (Phase 5). Each row links to the surface's autovalidate panel
 * where the user can preview deltas, apply, or dismiss.
 *
 * The component is intentionally self-contained — embed it anywhere
 * (sidebar, admin dashboard, modal). No props required.
 */
export function OptimizerInbox() {
  const [data, setData] = useState<OptimizerInboxResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getOptimizerInbox()
      .then(setData)
      .catch(e => console.error('getOptimizerInbox failed', e))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: '#888' }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }
  if (!data) return null

  const { items, counts } = data

  if (items.length === 0) {
    return (
      <div style={{
        padding: 20, background: '#1a1a1a',
        border: '1px solid #2e2e2e', borderRadius: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#bbb', fontSize: 13 }}>
          <Inbox size={14} />
          No quality candidates waiting for review.
        </div>
        <div style={{ marginTop: 4, fontSize: 11, color: '#666' }}>
          When the system detects a drop or elevated thumbs-down rate it'll
          auto-tune the affected item and surface a candidate fix here.
        </div>
      </div>
    )
  }

  return (
    <div>
      <header style={{
        display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10,
      }}>
        <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: '#fff' }}>
          Quality candidates
        </h3>
        <span style={{ fontSize: 11, color: '#888' }}>
          {counts.pending_review} ready · {counts.in_flight} in flight · {counts.applied} applied
        </span>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(it => <Row key={`${it.surface}:${it.run_uuid}`} item={it} />)}
      </div>
    </div>
  )
}

function Row({ item }: { item: OptimizerInboxItem }) {
  const score = item.score != null ? `${Math.round(item.score * 100)}` : '-'
  const baseline = item.baseline_score != null ? `${Math.round(item.baseline_score * 100)}` : '-'
  const lift = (item.score != null && item.baseline_score != null)
    ? (item.score - item.baseline_score) * 100
    : null

  const surfaceColor = item.surface === 'kb' ? '#a78bfa'
    : item.surface === 'extraction' ? '#22c55e'
    : '#3b82f6'

  const triggerLabel = item.trigger === 'cross_field_failure' ? 'workflow check fails'
    : item.trigger === 'chat_feedback_threshold' ? 'chat thumbs-down rate'
    : item.trigger === 'quality_alert' ? 'quality regression alert'
    : 'auto-trigger'

  const isApplied = !!item.applied_at && !item.reverted_at
  const isStale = item.tied_with_baseline

  return (
    <a
      href={item.link}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 12px', backgroundColor: '#1f1f1f',
        border: '1px solid #2e2e2e', borderRadius: 6,
        textDecoration: 'none', color: 'inherit',
        opacity: isApplied || isStale ? 0.65 : 1,
      }}
    >
      <span style={{
        padding: '2px 6px', fontSize: 10, fontWeight: 600,
        color: surfaceColor, background: surfaceColor + '14',
        borderRadius: 4, textTransform: 'uppercase', letterSpacing: 0.5,
      }}>
        {item.surface}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: '#e5e5e5', display: 'flex', alignItems: 'center', gap: 6 }}>
          {isApplied
            ? <CheckCircle2 size={11} style={{ color: '#22c55e' }} />
            : <Sparkles size={11} style={{ color: '#a78bfa' }} />}
          {isApplied
            ? `Applied · ${score} (was ${baseline})`
            : isStale
              ? `No measurable improvement vs current`
              : `Candidate · ${score} (was ${baseline})`}
          {lift != null && !isStale && (
            <span style={{ color: lift >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
              {lift >= 0 ? '+' : ''}{lift.toFixed(1)} pts
            </span>
          )}
        </div>
        <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>
          Triggered by {triggerLabel}
          {item.completed_at && ` · ${new Date(item.completed_at).toLocaleString()}`}
          {item.apply_preview && (
            <> · {item.apply_preview.will_change}/{item.apply_preview.total} items
              {item.apply_preview.regressions > 0 && (
                <span style={{ color: '#f97316' }}> · {item.apply_preview.regressions} regress</span>
              )}
            </>
          )}
        </div>
      </div>
      <ArrowRight size={14} style={{ color: '#666' }} />
    </a>
  )
}
