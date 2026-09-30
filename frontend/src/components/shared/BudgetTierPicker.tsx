import { Radio } from './Toggle'
import type { BudgetTier } from './budgetTiers'

interface BudgetTierPickerProps {
  tiers: readonly BudgetTier[]
  /** Selected tier id, or 'custom' when using a free-form token count. */
  selected: string
  onSelect: (id: string) => void
  customTokens: number
  onCustomTokens: (n: number) => void
  /** Pre-formatted budget label, e.g. "≈2.5M tokens". Caller controls formatting. */
  tokensLabel: string
  /** Pre-formatted cost label, e.g. "≈$5". Null when cost data unavailable. */
  costLabel: string | null
  /** Per-tier display formatter — caller decides how to render tokens/cost on each row. */
  formatTierRow: (tier: BudgetTier) => { tokensLabel: string; costLabel: string | null }
  /** When set, the matching tier renders a "Recommended for you" badge so
   * cold-start users have a sensible default based on their baseline probe. */
  recommendedTierId?: string
  /** Short caption shown alongside the recommendation badge, e.g. "Your model
   * already does well without the KB — a smaller budget is enough." */
  recommendationReason?: string
  title?: string
  description?: string
}

export function BudgetTierPicker({
  tiers, selected, onSelect, customTokens, onCustomTokens,
  tokensLabel, costLabel, formatTierRow,
  recommendedTierId, recommendationReason,
  title = 'Token budget',
  description = 'Each setup costs LLM tokens to test. The smaller tiers confirm whether tuning helps at all; larger tiers find a more confident winner.',
}: BudgetTierPickerProps) {
  return (
    <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)' }}>{title}</h4>
      <p style={{ margin: '0 0 12px 0', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>{description}</p>
      {recommendedTierId && recommendationReason && (
        <div style={{
          marginBottom: 10, padding: '8px 10px',
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, transparent)',
          border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, transparent)', borderRadius: 6,
          fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-accent-ink)', lineHeight: 1.5,
        }}>
          {recommendationReason}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {tiers.map(t => {
          const active = selected === t.id
          const recommended = recommendedTierId === t.id
          const { tokensLabel: rowTokens, costLabel: rowCost } = formatTierRow(t)
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', textAlign: 'left',
                backgroundColor: active ? 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, transparent)' : 'var(--workspace-surface)',
                border: '1px solid ' + (active ? 'var(--highlight-color, #eab308)' : 'var(--workspace-border)'),
                borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: 'var(--workspace-text)',
              }}
            >
              <Radio active={active} />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600 }}>{t.label}</div>
                  {recommended && (
                    <span style={{
                      fontSize: 'var(--workspace-font-meta)', fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase',
                      padding: '2px 6px', borderRadius: 10,
                      color: 'var(--workspace-accent-ink)', backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 18%, transparent)',
                      border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 45%, transparent)',
                    }}>
                      Recommended for you
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                  {rowTokens}
                  {rowCost && <> · {rowCost}</>}
                  {' · '}{t.trialsEstimate} · {t.timeEstimate}
                </div>
              </div>
            </button>
          )
        })}
        <button
          onClick={() => onSelect('custom')}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '10px 12px', textAlign: 'left',
            backgroundColor: selected === 'custom' ? 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, transparent)' : 'var(--workspace-surface)',
            border: '1px solid ' + (selected === 'custom' ? 'var(--highlight-color, #eab308)' : 'var(--workspace-border)'),
            borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: 'var(--workspace-text)',
          }}
        >
          <Radio active={selected === 'custom'} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600 }}>Custom</div>
            {selected === 'custom' && (
              <input
                type="number"
                value={customTokens}
                onChange={e => onCustomTokens(Math.max(0, Number(e.target.value) || 0))}
                onClick={e => e.stopPropagation()}
                style={{
                  marginTop: 4, width: 120,
                  background: 'var(--workspace-canvas)', color: 'var(--workspace-text)', border: '1px solid var(--workspace-border)',
                  borderRadius: 4, padding: '4px 6px', fontSize: 'var(--workspace-font-meta)',
                }}
              />
            )}
          </div>
        </button>
      </div>
      <div style={{
        marginTop: 12, padding: '8px 10px',
        backgroundColor: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)', borderRadius: 6,
        fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)',
      }}>
        Selected: <b>{tokensLabel}</b>{costLabel && <> · <b>{costLabel}</b></>}
      </div>
      <p style={{ margin: '8px 0 0 0', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
        Time estimates are approximate. Actual runtime scales with your test-set
        size and current model speed, so larger test sets can take noticeably longer.
      </p>
    </div>
  )
}
