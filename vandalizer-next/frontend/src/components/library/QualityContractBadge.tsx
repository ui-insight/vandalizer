import { relativeTime } from '../../utils/time'

interface QualityContractBadgeProps {
  status: string
  tier: string | null
  score: number | null
  lastValidatedAt: string | null
  isStale: boolean
  monitored: boolean
}

const statusColors: Record<string, { bg: string; text: string; border: string }> = {
  monitored: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
  stale: { bg: '#fffbeb', text: '#a16207', border: '#fde68a' },
  degraded: { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
  unmonitored: { bg: '#f9fafb', text: '#6b7280', border: '#e5e7eb' },
}

export function QualityContractBadge({ status, tier, lastValidatedAt, isStale, monitored }: QualityContractBadgeProps) {
  const effectiveStatus = isStale ? 'stale' : status
  const colors = statusColors[effectiveStatus] || statusColors.unmonitored

  const tierLabel = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : 'Unknown'
  const monitorLabel = monitored ? 'Monitored' : 'Unmonitored'
  const staleLabel = isStale && lastValidatedAt ? `Last checked ${relativeTime(lastValidatedAt)}` : ''

  let label = `Verified`
  if (tier) label += ` \u00b7 ${tierLabel}`
  if (isStale) {
    label += ` \u00b7 Stale`
    if (staleLabel) label += ` \u00b7 ${staleLabel}`
  } else {
    label += ` \u00b7 ${monitorLabel}`
  }

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
