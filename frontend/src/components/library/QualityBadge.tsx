import { qualityPresentation, type QualityEvidence } from '../../lib/qualityLabels'
import { validationDate } from './CatalogSignals'

export function QualityBadge({ tier, score, title, regressionPending = false, asserted = false,
  testCaseCount, lastValidatedAt, outdated = false, limitedEvidence, grade, needsReview = false,
}: QualityEvidence & {
  tier: string | null | undefined
  score: number | null
  title?: string
  regressionPending?: boolean
  variant?: 'quality' | 'catalog'
  lastValidatedAt?: string | null
}) {
  const quality = qualityPresentation({ tier, score, grade, asserted, testCaseCount, outdated, limitedEvidence, needsReview: regressionPending || needsReview })
  const date = validationDate(lastValidatedAt)
  return (
    <details onClick={event => event.stopPropagation()} style={{ display: 'inline-block', maxWidth: '100%', fontSize: 12, lineHeight: '18px', textAlign: 'left' }}>
      <summary aria-label={`${quality.label}. View evaluation`} style={{
        cursor: 'pointer', padding: '2px 6px', borderRadius: 4, overflowWrap: 'anywhere',
        border: `1px solid ${quality.colors.border}`, backgroundColor: quality.colors.bg, color: quality.colors.text,
      }}>
        <span style={{ fontWeight: 600 }}>{quality.label}</span>
        <span style={{ display: 'block', fontWeight: 400 }}>{quality.evidence}</span>
      </summary>
      <div role="region" aria-label="Evaluation details" style={{ padding: 8, color: '#374151', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 4, maxWidth: 340 }}>
        {quality.measured && <p style={{ margin: '0 0 4px' }}>Recorded score: {score != null && Number.isFinite(score) ? `${Math.round(score)}/100` : 'Not recorded'}{grade ? ` · Rubric grade: ${grade}` : ''}</p>}
        <p style={{ margin: '0 0 4px' }}>Examples: {quality.measured ? testCaseCount ?? 'Not recorded' : 'Not evaluated'} · Evaluated: {date || 'Not recorded'}</p>
        {regressionPending && <p>A regression is awaiting review. The previous rating no longer describes current performance.</p>}
        {outdated && <p>This evaluation may not describe the current configuration. Evaluate it again after reviewing changes.</p>}
        {quality.limited && <p>Limited evidence: inspect the examples and add representative cases before drawing broader conclusions.</p>}
        {asserted && <p>The author supplied a rating. No measured evaluation backs it here.</p>}
        {title && <p>{title}</p>}
        <p style={{ marginBottom: 0 }}>These results describe the examples tested. Inspect failed checks and coverage for your task; the score is not a guarantee for new inputs.</p>
      </div>
    </details>
  )
}
