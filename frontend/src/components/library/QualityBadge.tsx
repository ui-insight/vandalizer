const tierColors: Record<string, { bg: string; text: string; border: string }> = {
  excellent: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
  good: { bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
  fair: { bg: '#fefce8', text: '#a16207', border: '#fde68a' },
}

const defaultColor = { bg: '#f9fafb', text: '#6b7280', border: '#e5e7eb' }

// A regression the system has already detected outranks the tier the item used
// to hold. Leaving the old colour up would keep endorsing something monitoring
// has decided is broken, which is the one thing a quality badge must not do.
const regressionColor = { bg: '#fef2f2', text: '#b91c1c', border: '#fecaca' }

// A hand-typed catalog tier with no measured score behind it is a claim. It
// renders in the neutral style whatever the tier word says, so a seeded
// "excellent" cannot pass for one a validation run earned.
const ASSERTED_TITLE =
  'The rating came with the starter example from its author. Nobody here has run a ' +
  'validation on it yet — validate it to get a measured score.'

const REGRESSION_TITLE =
  'Automatic revalidation scored this materially lower than before. ' +
  'The previous rating no longer applies until someone reviews it.'

export function QualityBadge({
  tier,
  score,
  title,
  regressionPending = false,
  asserted = false,
  variant = 'quality',
}: {
  tier: string | null
  score: number | null
  title?: string
  regressionPending?: boolean
  /** The tier is a catalog assertion with no measured score — see ASSERTED_TITLE. */
  asserted?: boolean
  /** 'catalog': the badge on a shared entry, where a score means an examiner
   *  checked it — leads with "Checked" instead of "Quality:". */
  variant?: 'quality' | 'catalog'
}) {
  const colors = regressionPending
    ? regressionColor
    : tier && !asserted
      ? tierColors[tier] || defaultColor
      : defaultColor
  const tierLabel = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : null
  const catalog = variant === 'catalog'
  const baseLabel = tierLabel
    ? asserted
      ? `Rated ${tierLabel} by its author · not yet checked here`
      : `${catalog ? 'Checked' : 'Quality:'} ${catalog ? '· ' : ''}${tierLabel}${score != null ? ` (${Math.round(score)}%)` : ''}`
    : catalog ? 'Not yet checked here' : 'Unvalidated'
  const label = regressionPending ? 'Regression pending review' : baseLabel

  return (
    <span
      title={regressionPending ? REGRESSION_TITLE : asserted && tier ? ASSERTED_TITLE : title}
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
