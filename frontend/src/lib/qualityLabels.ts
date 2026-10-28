/** Presentation only: use the server's configured tiers or workflow rubric.
 * Never derive a common percentage threshold for different evaluation types. */
export interface QualityEvidence {
  tier?: string | null
  score?: number | null
  grade?: string | null
  asserted?: boolean
  testCaseCount?: number | null
  limitedEvidence?: boolean
  outdated?: boolean
  needsReview?: boolean
}

export const QUALITY_COLORS = {
  strong: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
  mixed: { bg: '#fffbeb', text: '#92400e', border: '#fde68a' },
  improvement: { bg: '#fff7ed', text: '#9a3412', border: '#fed7aa' },
  review: { bg: '#fef2f2', text: '#b91c1c', border: '#fecaca' },
  neutral: { bg: '#f9fafb', text: '#59616b', border: '#d1d5db' },
} as const

export function qualityPresentation(input: QualityEvidence) {
  const measured = !input.asserted && (Number.isFinite(input.score) || !!input.grade)
  const limited = measured && (input.limitedEvidence || (input.testCaseCount != null && input.testCaseCount < 5))
  let tone: keyof typeof QUALITY_COLORS = 'neutral'
  let label = 'Not evaluated'
  if (measured) {
    const tier = input.tier?.toLowerCase()
    if (tier === 'excellent' || tier === 'good' || (!tier && ['A', 'B'].includes(input.grade || ''))) {
      label = 'Strong on tested examples'; tone = 'strong'
    } else if (tier === 'fair' || (!tier && input.grade === 'C')) {
      label = 'Mixed results'; tone = 'mixed'
    } else if (tier === 'poor' || (input.tier === null && Number.isFinite(input.score)) || ['D', 'F'].includes(input.grade || '')) {
      // The backend returns a null tier for a measured score below its fair threshold.
      label = 'Needs improvement'; tone = 'improvement'
    } else {
      label = 'Evaluation recorded'
    }
  }
  if (input.outdated && measured) { label = 'Evaluation outdated'; tone = 'mixed' }
  if (input.needsReview) { label = 'Needs review'; tone = 'review' }
  const evidence = input.asserted ? 'Author rating · no measured evaluation'
    : !measured ? 'No measured evaluation available'
    : limited ? 'Limited evidence'
    : input.testCaseCount == null ? 'Sample size not recorded'
    : `Tested on ${input.testCaseCount} examples`
  return { label, evidence, measured, limited: !!limited, tone, colors: QUALITY_COLORS[tone] }
}

export function assertedTierNote(tier: string | null | undefined): string | null {
  return tier ? 'Author rating · not evaluated here' : null
}
