const tierColors: Record<string, { bg: string; text: string; border: string }> = {
  excellent: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
  good: { bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
  fair: { bg: '#fefce8', text: '#a16207', border: '#fde68a' },
}

const defaultColor = { bg: '#f9fafb', text: '#6b7280', border: '#e5e7eb' }

export function QualityBadge({ tier, score }: { tier: string | null; score: number | null }) {
  const colors = tier ? tierColors[tier] || defaultColor : defaultColor
  const label = tier ? `${tier.charAt(0).toUpperCase() + tier.slice(1)}${score != null ? ` (${Math.round(score)}%)` : ''}` : 'Unvalidated'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        fontSize: '11px',
        lineHeight: '16px',
        padding: '1px 6px',
        borderRadius: '4px',
        border: `1px solid ${colors.border}`,
        backgroundColor: colors.bg,
        color: colors.text,
        fontWeight: 500,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}
