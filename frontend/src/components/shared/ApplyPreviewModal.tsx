import { usePanelEffect } from './usePanelEffect'
import { useEffect, useLayoutEffect, useState, useMemo, useRef } from 'react'
import { FocusTrap } from './PanelFocusTrap'
import { AlertTriangle, CheckCircle2, MinusCircle, X } from 'lucide-react'

/** Generic per-item entry — matches ``optimization_common.build_apply_preview``. */
export interface ApplyPreviewItem {
  item_id: string | null
  label: string | null
  baseline: number
  winner: number
  delta: number
  within_noise: boolean
  is_regression: boolean
  significant: boolean
}

export interface ApplyPreview {
  total: number
  will_change: number
  improvements: number
  regressions: number
  significant_regressions: number
  net_delta: number
  noise_sigma: number | null
  items: ApplyPreviewItem[]
}

interface Props {
  open: boolean
  preview: ApplyPreview
  /** Singular noun for an "item" — "query", "field", "step". */
  itemNoun: string
  /** Plural noun for an "item" — "queries", "fields", "steps". */
  itemNounPlural: string
  /** Called when the user confirms the apply. */
  onConfirm: () => void
  onCancel: () => void
  applying: boolean
  error?: string | null
}

/**
 * Pre-Apply confirmation modal.
 *
 * Renders the per-item baseline-vs-winner preview so users see exactly what
 * the apply will change — and how many items regress — before committing.
 * Significant regressions (|delta| > 2σ) force an "I understand" checkbox
 * before the confirm button enables.
 */
export function ApplyPreviewModal({
  open, preview, itemNoun, itemNounPlural, onConfirm, onCancel, applying, error,
}: Props) {
  const errorRef = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (error) errorRef.current?.scrollIntoView({ block: 'nearest' }) }, [error])
  const [ack, setAck] = useState(false)
  const requiresAck = preview.significant_regressions > 0
  const canConfirm = (!requiresAck || ack) && !applying

  const sortedItems = useMemo(() => {
    // Regressions first (most severe), then improvements, then no-ops.
    return [...preview.items].sort((a, b) => {
      if (a.is_regression !== b.is_regression) return a.is_regression ? -1 : 1
      return a.delta - b.delta
    })
  }, [preview.items])

  usePanelEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape' && !applying) onCancel() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel, applying])

  useLayoutEffect(() => { if (open) setAck(false) }, [open, preview])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm apply"
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={() => { if (!applying) onCancel() }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, 92vw)',
          maxHeight: 'calc(100dvh - 24px)', overflow: 'hidden', overflowWrap: 'anywhere',
          background: 'var(--workspace-canvas)',
          border: '1px solid var(--workspace-border)',
          borderRadius: 10,
          display: 'flex', flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        <header style={{
          padding: '12px 18px', flexShrink: 0,
          borderBottom: '1px solid var(--workspace-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)' }}>
              Confirm apply
            </span>
          </div>
          <button
            aria-label="Close"
            onClick={onCancel}
            disabled={applying}
            style={{
              background: 'transparent', border: 'none', color: 'var(--workspace-muted)',
              cursor: applying ? 'not-allowed' : 'pointer', padding: 4, minWidth: 36, minHeight: 36,
            }}
          >
            <X size={16} />
          </button>
        </header>

        <div role="region" aria-label="Apply review details" tabIndex={0} style={{ minHeight: 0, overflowY: 'auto' }}>
        {/* Summary chips */}
        <div style={{ padding: '14px 18px 8px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <SummaryChip
            color="var(--workspace-info)"
            label={`${preview.will_change} of ${preview.total} ${itemNounPlural} will change`}
          />
          <SummaryChip
            icon={<CheckCircle2 size={11} />}
            color="var(--workspace-success)"
            label={`${preview.improvements} improve`}
          />
          <SummaryChip
            icon={<MinusCircle size={11} />}
            color={preview.regressions > 0 ? 'var(--workspace-warning)' : 'var(--workspace-muted)'}
            label={`${preview.regressions} regress`}
          />
          {preview.significant_regressions > 0 && (
            <SummaryChip
              icon={<AlertTriangle size={11} />}
              color="var(--workspace-danger)"
              label={`${preview.significant_regressions} > judge noise`}
            />
          )}
          <SummaryChip
            color={preview.net_delta >= 0 ? 'var(--workspace-success)' : 'var(--workspace-danger)'}
            label={`Net Δ ${preview.net_delta >= 0 ? '+' : ''}${(preview.net_delta * 100).toFixed(1)} pts`}
          />
        </div>

        <p style={{ padding: '0 18px', margin: '4px 0 10px', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>These are recorded test scores for the current and proposed settings. Applying changes retrieval settings; it does not guarantee the same scores on future questions.</p>
        {/* Items table */}
        <div style={{ flexShrink: 0, padding: '4px 18px 12px' }}>
          {sortedItems.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--workspace-muted)', fontSize: 'var(--workspace-font-meta)' }}>
              No per-{itemNoun} detail available for this run.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {sortedItems.map((item, idx) => (
                <li key={item.item_id || idx} style={{ padding: 12, color: 'var(--workspace-text)', border: '1px solid var(--workspace-border)', borderRadius: 6, background: item.significant && item.is_regression ? 'rgba(239,68,68,0.06)' : undefined }}>
                  <p style={{ margin: '0 0 8px', fontSize: 'var(--workspace-font-control)', lineHeight: 1.5 }}>{item.label || item.item_id || `${capitalize(itemNoun)} ${idx + 1}`}</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', fontSize: 'var(--workspace-font-meta)', fontVariantNumeric: 'tabular-nums' }}>
                    <span>Current: <strong>{(item.baseline * 100).toFixed(0)}</strong></span>
                    <span>Proposed: <strong>{(item.winner * 100).toFixed(0)}</strong></span>
                    <span style={{ color: item.within_noise ? 'var(--workspace-muted)' : item.is_regression ? 'var(--workspace-danger)' : 'var(--workspace-success)' }}>Change: {item.delta > 0 ? '+' : ''}{(item.delta * 100).toFixed(1)} points</span>
                    {item.significant && !item.within_noise && <span>{item.is_regression ? 'Significant regression' : 'Significant improvement'}</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Acknowledgement + actions */}
        <div style={{
          padding: '12px 18px',
          borderTop: '1px solid var(--workspace-border)',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          {requiresAck && (
            <label style={{
              display: 'flex', gap: 8, alignItems: 'flex-start',
              fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-warning)',
            }}>
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
                disabled={applying}
                style={{ marginTop: 2 }}
              />
              <span>
                I've reviewed the {preview.significant_regressions} significant
                regression{preview.significant_regressions === 1 ? '' : 's'} above
                and want to apply anyway.
              </span>
            </label>
          )}
          {error && <p ref={errorRef} role="alert" style={{ margin: '0 0 12px', padding: 10, fontSize: 'var(--workspace-font-control)', lineHeight: 1.5, color: 'var(--workspace-danger)', background: 'var(--workspace-danger-surface)', borderRadius: 6 }}>{error} Review the result and try again.</p>}
        </div>
        </div>
        <footer style={{ flexShrink: 0, padding: '12px 18px', borderTop: '1px solid var(--workspace-border)' }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              onClick={onCancel}
              disabled={applying}
              style={{
                minHeight: 36, padding: '6px 14px', fontSize: 'var(--workspace-font-body)', fontWeight: 500,
                color: 'var(--workspace-muted)', background: 'transparent',
                border: '1px solid var(--workspace-border)', borderRadius: 6,
                cursor: applying ? 'not-allowed' : 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={!canConfirm}
              style={{
                minHeight: 36, padding: '6px 14px', fontSize: 'var(--workspace-font-body)', fontWeight: 600,
                color: canConfirm ? 'var(--highlight-text-color, #000)' : 'var(--workspace-muted)',
                background: canConfirm
                  ? 'var(--highlight-color, #eab308)'
                  : 'var(--workspace-surface)',
                border: '1px solid ' + (canConfirm ? 'var(--highlight-color, #eab308)' : 'var(--workspace-border)'),
                borderRadius: 6,
                cursor: canConfirm ? 'pointer' : 'not-allowed',
              }}
            >
              {applying ? 'Applying…' : 'Apply'}
            </button>
          </div>
        </footer>
      </div>
      </FocusTrap>
    </div>
  )
}

function SummaryChip({
  icon, color, label,
}: { icon?: React.ReactNode; color: string; label: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 8px',
      fontSize: 'var(--workspace-font-meta)', color,
      background: 'var(--workspace-canvas)',
      border: '1px solid ' + color + '40',
      borderRadius: 999,
    }}>
      {icon}
      {label}
    </span>
  )
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
