import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  Inbox,
  Loader2,
  MinusCircle,
  RotateCcw,
  Sparkles,
  Undo2,
  Workflow as WorkflowIcon,
  ListChecks,
  X,
} from 'lucide-react'
import {
  dismissOptimizerCandidate,
  getOptimizerInbox,
  restoreOptimizerCandidate,
  type OptimizerInboxCategory,
  type OptimizerInboxItem,
  type OptimizerInboxResponse,
  type OptimizerSurface,
} from '../../api/optimizerInbox'
import { applyKBOptimization } from '../../api/knowledge'
import { applyExtractionOptimization } from '../../api/extractions'
import { applyWorkflowOptimization } from '../../api/workflows'
import { ApplyPreviewModal } from './ApplyPreviewModal'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from './useConfirm'
import { relativeTime } from '../../utils/time'

/**
 * Optimizer Inbox — the review surface for automatically generated tuning
 * suggestions, plus the tuning runs that failed.
 *
 * Auto-triggered ("shadow") optimizer runs finish with a winning config that
 * nothing ever asked a human to look at. This lists them per item the caller
 * can see, shows the expected impact, and offers Apply / Dismiss.
 *
 * Apply deliberately calls the per-surface apply endpoint each panel uses, so
 * the same governance gates (tied-with-baseline, cross-field thresholds,
 * revert snapshots, quality-timeline recording) apply here too.
 */

const SURFACE_META: Record<OptimizerSurface, {
  label: string
  color: string
  icon: typeof BookOpen
  itemNoun: string
  itemNounPlural: string
  openLabel: string
}> = {
  kb: {
    label: 'Knowledge base', color: '#7c3aed', icon: BookOpen,
    itemNoun: 'query', itemNounPlural: 'queries', openLabel: 'Open knowledge base',
  },
  extraction: {
    label: 'Extraction set', color: '#166534', icon: ListChecks,
    itemNoun: 'field', itemNounPlural: 'fields', openLabel: 'Open extraction set',
  },
  workflow: {
    label: 'Workflow', color: '#0050d7', icon: WorkflowIcon,
    itemNoun: 'step', itemNounPlural: 'steps', openLabel: 'Open workflow',
  },
}

const TRIGGER_LABEL: Record<string, string> = {
  cross_field_failure: 'cross-field checks were failing',
  chat_feedback_threshold: 'chat answers were getting thumbs-down',
  quality_alert: 'a quality regression alert fired',
}

const CATEGORY_ORDER: OptimizerInboxCategory[] = [
  'needs_review', 'failed', 'in_flight', 'applied', 'no_change', 'cancelled', 'dismissed',
]

const CATEGORY_META: Record<OptimizerInboxCategory, { title: string; blurb: string }> = {
  needs_review: {
    title: 'Ready to review',
    blurb: 'A tuning run found a better configuration. Nothing changes until you apply it.',
  },
  failed: {
    title: 'Tuning failed',
    blurb: 'These runs stopped before producing a suggestion.',
  },
  in_flight: { title: 'Tuning now', blurb: 'Runs still in progress.' },
  applied: { title: 'Applied', blurb: 'These configurations are live on the item.' },
  no_change: {
    title: 'No change recommended',
    blurb: 'The best configuration found was no better than the current one.',
  },
  cancelled: { title: 'Cancelled', blurb: 'Runs cancelled before finishing.' },
  dismissed: { title: 'Dismissed', blurb: 'Suggestions you decided against.' },
}

function pct(score: number | null): string {
  return score == null ? '—' : `${Math.round(score * 100)}`
}

function triggerSentence(item: OptimizerInboxItem): string {
  if (!item.trigger) return 'Tuned on request'
  const reason = TRIGGER_LABEL[item.trigger] || 'the system flagged a quality signal'
  return `Auto-tuned because ${reason}`
}

export function OptimizerInbox() {
  const { toast } = useToast()
  const confirm = useConfirm()
  const [data, setData] = useState<OptimizerInboxResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showDismissed, setShowDismissed] = useState(false)
  const [busyRun, setBusyRun] = useState<string | null>(null)
  const [previewFor, setPreviewFor] = useState<OptimizerInboxItem | null>(null)

  const load = useCallback(async (includeDismissed: boolean) => {
    setLoading(true)
    setError(null)
    try {
      setData(await getOptimizerInbox({ includeDismissed }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tuning suggestions')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load(showDismissed) }, [load, showDismissed])

  const applyItem = useCallback(async (item: OptimizerInboxItem) => {
    setBusyRun(item.run_uuid)
    try {
      if (item.surface === 'kb') {
        await applyKBOptimization(item.item_id, item.run_uuid)
      } else if (item.surface === 'extraction') {
        await applyExtractionOptimization(item.item_id, item.run_uuid)
      } else {
        await applyWorkflowOptimization(item.item_id, item.run_uuid)
      }
      toast(`Applied to ${item.item_name}`, 'success')
      setPreviewFor(null)
      await load(showDismissed)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Apply failed', 'error')
    } finally {
      setBusyRun(null)
    }
  }, [toast, load, showDismissed])

  const handleApplyClick = useCallback(async (item: OptimizerInboxItem) => {
    // Runs from before apply-preview existed have nothing to show in the
    // preview modal, so fall back to a plain confirmation.
    if (item.apply_preview && item.apply_preview.items.length > 0) {
      setPreviewFor(item)
      return
    }
    const ok = await confirm({
      title: 'Apply this configuration?',
      message: `This replaces the current configuration of "${item.item_name}". You can revert it afterwards from the item's Validate & improve tab.`,
      confirmLabel: 'Apply',
    })
    if (ok) await applyItem(item)
  }, [confirm, applyItem])

  const handleDismiss = useCallback(async (item: OptimizerInboxItem) => {
    setBusyRun(item.run_uuid)
    try {
      await dismissOptimizerCandidate(item.surface, item.run_uuid)
      await load(showDismissed)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Dismiss failed', 'error')
    } finally {
      setBusyRun(null)
    }
  }, [toast, load, showDismissed])

  const handleRestore = useCallback(async (item: OptimizerInboxItem) => {
    setBusyRun(item.run_uuid)
    try {
      await restoreOptimizerCandidate(item.surface, item.run_uuid)
      await load(showDismissed)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Restore failed', 'error')
    } finally {
      setBusyRun(null)
    }
  }, [toast, load, showDismissed])

  const grouped = useMemo(() => {
    const groups = new Map<OptimizerInboxCategory, OptimizerInboxItem[]>()
    for (const item of data?.items || []) {
      const list = groups.get(item.category) || []
      list.push(item)
      groups.set(item.category, list)
    }
    return groups
  }, [data])

  if (loading && !data) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: '#6b7280' }}>
        <Loader2 className="animate-spin" style={{ width: 18, height: 18, margin: '0 auto' }} />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: 16,
        background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
        color: '#991b1b', fontSize: 13,
      }}>
        <AlertTriangle style={{ width: 16, height: 16, flexShrink: 0 }} />
        <span style={{ flex: 1 }}>{error}</span>
        <button onClick={() => void load(showDismissed)} style={secondaryButton}>Retry</button>
      </div>
    )
  }

  const counts = data?.counts
  const hasRows = (data?.items.length || 0) > 0

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        flexWrap: 'wrap', marginBottom: 16,
      }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Stat label="Ready to review" value={counts?.needs_review ?? 0} tone="action" />
          <Stat label="Failed" value={counts?.failed ?? 0} tone={counts?.failed ? 'bad' : 'neutral'} />
          <Stat label="Tuning now" value={counts?.in_flight ?? 0} tone="neutral" />
          <Stat label="Applied" value={counts?.applied ?? 0} tone="good" />
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 12, color: '#4b5563', cursor: 'pointer',
          }}>
            <input
              type="checkbox"
              checked={showDismissed}
              onChange={e => setShowDismissed(e.target.checked)}
            />
            Show dismissed
          </label>
          <button onClick={() => void load(showDismissed)} style={secondaryButton} disabled={loading}>
            <RotateCcw style={{ width: 12, height: 12 }} />
            Refresh
          </button>
        </div>
      </div>

      {!hasRows ? (
        <div style={{
          padding: 24, background: '#fff', border: '1px solid #e5e7eb',
          borderRadius: 8, textAlign: 'center',
        }}>
          <Inbox style={{ width: 20, height: 20, color: '#9ca3af', margin: '0 auto 8px' }} />
          <div style={{ fontSize: 14, color: '#374151', fontWeight: 600 }}>
            Nothing waiting for review
          </div>
          <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280', maxWidth: 460, margin: '4px auto 0' }}>
            When quality slips on a workflow, extraction set, or knowledge base, the
            system tunes it in the background and the candidate fix shows up here.
            Failed tuning runs show up here too.
          </div>
        </div>
      ) : (
        CATEGORY_ORDER.map(category => {
          const items = grouped.get(category)
          if (!items?.length) return null
          const meta = CATEGORY_META[category]
          return (
            <section key={category} style={{ marginBottom: 24 }}>
              <h2 style={{
                fontSize: 13, fontWeight: 700, color: '#111827',
                margin: '0 0 2px', display: 'flex', alignItems: 'center', gap: 6,
              }}>
                {meta.title}
                <span style={{ fontWeight: 500, color: '#6b7280' }}>({items.length})</span>
              </h2>
              <p style={{ fontSize: 12, color: '#6b7280', margin: '0 0 8px' }}>{meta.blurb}</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {items.map(item => (
                  <Row
                    key={`${item.surface}:${item.run_uuid}`}
                    item={item}
                    busy={busyRun === item.run_uuid}
                    onApply={() => void handleApplyClick(item)}
                    onDismiss={() => void handleDismiss(item)}
                    onRestore={() => void handleRestore(item)}
                  />
                ))}
              </div>
            </section>
          )
        })
      )}

      {data && (
        <p style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
          Showing the last {data.lookback_days} days. Older runs stay in each item's
          Validate &amp; improve history.
        </p>
      )}

      {previewFor?.apply_preview && (
        <ApplyPreviewModal
          open
          preview={previewFor.apply_preview}
          itemNoun={SURFACE_META[previewFor.surface].itemNoun}
          itemNounPlural={SURFACE_META[previewFor.surface].itemNounPlural}
          applying={busyRun === previewFor.run_uuid}
          onConfirm={() => void applyItem(previewFor)}
          onCancel={() => setPreviewFor(null)}
        />
      )}
    </div>
  )
}

function Row({ item, busy, onApply, onDismiss, onRestore }: {
  item: OptimizerInboxItem
  busy: boolean
  onApply: () => void
  onDismiss: () => void
  onRestore: () => void
}) {
  const meta = SURFACE_META[item.surface]
  const Icon = meta.icon
  const lift = (item.score != null && item.baseline_score != null)
    ? (item.score - item.baseline_score) * 100
    : null
  const when = item.completed_at || item.started_at
  const preview = item.apply_preview
  const isFailed = item.category === 'failed'
  const isDismissed = item.category === 'dismissed'
  const canAct = item.can_manage && !busy

  return (
    <article style={{
      background: '#fff',
      border: `1px solid ${isFailed ? '#fecaca' : '#e5e7eb'}`,
      borderRadius: 8, padding: '12px 14px',
      opacity: isDismissed ? 0.7 : 1,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span
          title={meta.label}
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 26, height: 26, borderRadius: 6, flexShrink: 0,
            background: `${meta.color}14`, color: meta.color,
          }}
        >
          <Icon style={{ width: 14, height: 14 }} />
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
              {item.item_name}
            </span>
            <span style={{ fontSize: 11, color: '#6b7280' }}>{meta.label}</span>
            {when && (
              <span style={{ fontSize: 11, color: '#9ca3af' }}>· {relativeTime(when)}</span>
            )}
          </div>

          <div style={{ fontSize: 12, color: '#4b5563', marginTop: 3 }}>
            {triggerSentence(item)}
          </div>

          {isFailed ? (
            <div style={{
              marginTop: 8, padding: '8px 10px', background: '#fef2f2',
              borderRadius: 6, fontSize: 12, color: '#991b1b',
            }}>
              <strong style={{ fontWeight: 600 }}>
                {item.error_code ? item.error_code.replace(/_/g, ' ') : 'Run failed'}
              </strong>
              {item.error_message && (
                <div style={{ marginTop: 2, color: '#7f1d1d', wordBreak: 'break-word' }}>
                  {item.error_message}
                </div>
              )}
            </div>
          ) : item.category === 'in_flight' ? (
            <div style={{ marginTop: 6, fontSize: 12, color: '#0050d7', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Loader2 className="animate-spin" style={{ width: 12, height: 12 }} />
              {item.progress_message || item.phase || 'Running'}
            </div>
          ) : (
            <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <span style={{
                fontSize: 12, color: '#374151', fontVariantNumeric: 'tabular-nums',
              }}>
                Score {pct(item.baseline_score)} → <strong>{pct(item.score)}</strong>
              </span>
              {lift != null && (
                <span style={{
                  fontSize: 12, fontWeight: 600,
                  color: lift > 0 ? '#166534' : lift < 0 ? '#b3261e' : '#6b7280',
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  {lift > 0 ? '+' : ''}{lift.toFixed(1)} pts
                </span>
              )}
              {preview && (
                <span style={{ fontSize: 12, color: '#4b5563' }}>
                  {preview.will_change} of {preview.total} {meta.itemNounPlural} change
                  {preview.regressions > 0 && (
                    <span style={{ color: '#9a3412' }}>
                      {' '}· {preview.regressions} regress
                      {preview.significant_regressions > 0 && ' (some beyond noise)'}
                    </span>
                  )}
                </span>
              )}
              {item.overfitting_warning && (
                <span
                  title="Too few test items to hold any back, so the score is measured on the same data the tuner optimized against."
                  style={{ fontSize: 11, color: '#9a3412', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  <AlertTriangle style={{ width: 11, height: 11 }} />
                  in-sample score
                </span>
              )}
            </div>
          )}

          {item.category === 'applied' && (
            <div style={{ marginTop: 6, fontSize: 12, color: '#166534', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <CheckCircle2 style={{ width: 12, height: 12 }} />
              Live on this item{item.applied_at ? ` since ${relativeTime(item.applied_at)}` : ''}
            </div>
          )}

          {item.category === 'no_change' && (
            <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <MinusCircle style={{ width: 12, height: 12 }} />
              Statistically tied with the current settings — nothing to apply.
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'stretch' }}>
          {item.category === 'needs_review' && item.can_manage && (
            <button onClick={onApply} disabled={!canAct} style={primaryButton}>
              {busy ? <Loader2 className="animate-spin" style={{ width: 12, height: 12 }} /> : <Sparkles style={{ width: 12, height: 12 }} />}
              Review &amp; apply
            </button>
          )}
          {item.category === 'needs_review' && item.can_manage && (
            <button onClick={onDismiss} disabled={!canAct} style={secondaryButton}>
              <X style={{ width: 12, height: 12 }} />
              Dismiss
            </button>
          )}
          {isFailed && item.can_manage && (
            <button onClick={onDismiss} disabled={!canAct} style={secondaryButton}>
              <X style={{ width: 12, height: 12 }} />
              Dismiss
            </button>
          )}
          {isDismissed && item.can_manage && (
            <button onClick={onRestore} disabled={!canAct} style={secondaryButton}>
              <Undo2 style={{ width: 12, height: 12 }} />
              Restore
            </button>
          )}
          <a href={item.link} style={{ ...secondaryButton, textDecoration: 'none' }}>
            <ExternalLink style={{ width: 12, height: 12 }} />
            Open
          </a>
        </div>
      </div>
    </article>
  )
}

function Stat({ label, value, tone }: {
  label: string
  value: number
  tone: 'action' | 'good' | 'bad' | 'neutral'
}) {
  const colors: Record<string, { bg: string; fg: string }> = {
    action: { bg: '#fef3c7', fg: '#92400e' },
    good: { bg: '#dcfce7', fg: '#166534' },
    bad: { bg: '#fee2e2', fg: '#991b1b' },
    neutral: { bg: '#f3f4f6', fg: '#374151' },
  }
  const c = colors[tone]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 10px', borderRadius: 999,
      background: c.bg, color: c.fg, fontSize: 12, fontWeight: 600,
    }}>
      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</span>
      <span style={{ fontWeight: 500 }}>{label}</span>
    </span>
  )
}

const baseButton: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 5,
  padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
  cursor: 'pointer', whiteSpace: 'nowrap',
}

const primaryButton: React.CSSProperties = {
  ...baseButton,
  background: '#111827', color: '#fff', border: '1px solid #111827',
}

const secondaryButton: React.CSSProperties = {
  ...baseButton,
  background: '#fff', color: '#374151', border: '1px solid #d1d5db',
}
