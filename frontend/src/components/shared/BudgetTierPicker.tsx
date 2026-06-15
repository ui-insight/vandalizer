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
    <div style={{ fontSize: 13, color: '#ccc' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: 13, color: '#fff' }}>{title}</h4>
      <p style={{ margin: '0 0 12px 0', color: '#bbb', lineHeight: 1.5 }}>{description}</p>
      {recommendedTierId && recommendationReason && (
        <div style={{
          marginBottom: 10, padding: '8px 10px',
          backgroundColor: 'rgba(124, 58, 237, 0.08)',
          border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 6,
          fontSize: 11, color: '#c4b5fd', lineHeight: 1.5,
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
                backgroundColor: active ? 'rgba(124, 58, 237, 0.12)' : '#262626',
                border: '1px solid ' + (active ? '#7c3aed' : '#333'),
                borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
              }}
            >
              <Radio active={active} />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{t.label}</div>
                  {recommended && (
                    <span style={{
                      fontSize: 9, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase',
                      padding: '2px 6px', borderRadius: 10,
                      color: '#a78bfa', backgroundColor: 'rgba(124, 58, 237, 0.18)',
                      border: '1px solid rgba(124, 58, 237, 0.45)',
                    }}>
                      Recommended for you
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: '#888' }}>
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
            backgroundColor: selected === 'custom' ? 'rgba(124, 58, 237, 0.12)' : '#262626',
            border: '1px solid ' + (selected === 'custom' ? '#7c3aed' : '#333'),
            borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit', color: '#e5e5e5',
          }}
        >
          <Radio active={selected === 'custom'} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Custom</div>
            {selected === 'custom' && (
              <input
                type="number"
                value={customTokens}
                onChange={e => onCustomTokens(Math.max(0, Number(e.target.value) || 0))}
                onClick={e => e.stopPropagation()}
                style={{
                  marginTop: 4, width: 120,
                  background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
                  borderRadius: 4, padding: '4px 6px', fontSize: 12,
                }}
              />
            )}
          </div>
        </button>
      </div>
      <div style={{
        marginTop: 12, padding: '8px 10px',
        backgroundColor: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 6,
        fontSize: 12, color: '#aaa',
      }}>
        Selected: <b>{tokensLabel}</b>{costLabel && <> · <b>{costLabel}</b></>}
      </div>
      <p style={{ margin: '8px 0 0 0', fontSize: 11, color: '#777', lineHeight: 1.5 }}>
        Time estimates are approximate — actual runtime scales with your test-set
        size and current model speed, so larger test sets can take noticeably longer.
      </p>
    </div>
  )
}
