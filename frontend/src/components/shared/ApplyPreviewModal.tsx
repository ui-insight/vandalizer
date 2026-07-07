import { useEffect, useState, useMemo } from 'react'
import { FocusTrap } from 'focus-trap-react'
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
  open, preview, itemNoun, itemNounPlural, onConfirm, onCancel, applying,
}: Props) {
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

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

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
      onClick={onCancel}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, 92vw)',
          maxHeight: '88vh',
          background: '#1a1a1a',
          border: '1px solid #2e2e2e',
          borderRadius: 10,
          display: 'flex', flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        <header style={{
          padding: '14px 18px',
          borderBottom: '1px solid #2e2e2e',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>
              Confirm apply
            </span>
          </div>
          <button
            aria-label="Close"
            onClick={onCancel}
            disabled={applying}
            style={{
              background: 'transparent', border: 'none', color: '#888',
              cursor: applying ? 'not-allowed' : 'pointer', padding: 4,
            }}
          >
            <X size={16} />
          </button>
        </header>

        {/* Summary chips */}
        <div style={{ padding: '14px 18px 8px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <SummaryChip
            color="#a78bfa"
            label={`${preview.will_change} of ${preview.total} ${itemNounPlural} will change`}
          />
          <SummaryChip
            icon={<CheckCircle2 size={11} />}
            color="#22c55e"
            label={`${preview.improvements} improve`}
          />
          <SummaryChip
            icon={<MinusCircle size={11} />}
            color={preview.regressions > 0 ? '#f97316' : '#888'}
            label={`${preview.regressions} regress`}
          />
          {preview.significant_regressions > 0 && (
            <SummaryChip
              icon={<AlertTriangle size={11} />}
              color="#ef4444"
              label={`${preview.significant_regressions} > judge noise`}
            />
          )}
          <SummaryChip
            color={preview.net_delta >= 0 ? '#22c55e' : '#ef4444'}
            label={`Net Δ ${preview.net_delta >= 0 ? '+' : ''}${(preview.net_delta * 100).toFixed(1)} pts`}
          />
        </div>

        {/* Items table */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 18px 12px' }}>
          {sortedItems.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#888', fontSize: 12 }}>
              No per-{itemNoun} detail available for this run.
            </div>
          ) : (
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ color: '#888', textAlign: 'left' }}>
                  <th scope="col" style={{ padding: '6px 8px', fontWeight: 500 }}>{capitalize(itemNoun)}</th>
                  <th scope="col" style={{ padding: '6px 8px', fontWeight: 500, textAlign: 'right' }}>Current</th>
                  <th scope="col" style={{ padding: '6px 8px', fontWeight: 500, textAlign: 'right' }}>After apply</th>
                  <th scope="col" style={{ padding: '6px 8px', fontWeight: 500, textAlign: 'right' }}>Δ</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item, idx) => (
                  <tr
                    key={item.item_id || idx}
                    style={{
                      borderTop: '1px solid #262626',
                      color: '#e5e5e5',
                      background: item.significant && item.is_regression ? 'rgba(239,68,68,0.06)' : undefined,
                    }}
                  >
                    <td style={{ padding: '6px 8px' }}>
                      {item.label || item.item_id || `Item ${idx + 1}`}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {(item.baseline * 100).toFixed(0)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {(item.winner * 100).toFixed(0)}
                    </td>
                    <td style={{
                      padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums',
                      color: item.within_noise ? '#888'
                        : item.is_regression ? (item.significant ? '#ef4444' : '#f97316')
                        : '#22c55e',
                    }}>
                      {item.delta > 0 ? '+' : ''}{(item.delta * 100).toFixed(1)}
                      {item.significant && !item.within_noise ? '*' : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Acknowledgement + actions */}
        <footer style={{
          padding: '12px 18px',
          borderTop: '1px solid #2e2e2e',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          {requiresAck && (
            <label style={{
              display: 'flex', gap: 8, alignItems: 'flex-start',
              fontSize: 12, color: '#fbbf24',
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
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              onClick={onCancel}
              disabled={applying}
              style={{
                padding: '6px 14px', fontSize: 12, fontWeight: 500,
                color: '#bbb', background: 'transparent',
                border: '1px solid #3a3a3a', borderRadius: 6,
                cursor: applying ? 'not-allowed' : 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={!canConfirm}
              style={{
                padding: '6px 14px', fontSize: 12, fontWeight: 600,
                color: canConfirm ? '#fff' : '#555',
                background: canConfirm
                  ? 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)'
                  : '#222',
                border: '1px solid ' + (canConfirm ? '#7c3aed' : '#333'),
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
      fontSize: 11, color,
      background: 'rgba(255,255,255,0.03)',
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
