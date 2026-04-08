import type { QualityMeta } from '../../types/chat'

const TIER_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  excellent: { bg: 'rgba(234,179,8,0.12)', border: '#eab308', text: '#a16207' },
  good: { bg: 'rgba(34,197,94,0.12)', border: '#22c55e', text: '#15803d' },
  fair: { bg: 'rgba(148,163,184,0.12)', border: '#94a3b8', text: '#475569' },
}

const DEFAULT_STYLE = { bg: 'rgba(148,163,184,0.08)', border: '#cbd5e1', text: '#64748b' }

export function QualityBadge({ quality }: { quality: QualityMeta }) {
  if (quality.score == null && !quality.tier) return null

  const tier = quality.tier?.toLowerCase() ?? ''
  const style = TIER_STYLES[tier] || DEFAULT_STYLE
  const label = quality.tier
    ? `${quality.tier.charAt(0).toUpperCase() + quality.tier.slice(1)}`
    : 'Unscored'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 9999,
        fontSize: 11,
        fontWeight: 500,
        lineHeight: '18px',
        background: style.bg,
        border: `1px solid ${style.border}`,
        color: style.text,
      }}
    >
      {quality.score != null && (
        <span style={{ fontWeight: 600 }}>{Math.round(quality.score)}</span>
      )}
      <span>{label}</span>
    </span>
  )
}
