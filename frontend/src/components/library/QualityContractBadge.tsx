import { QualityBadge } from './QualityBadge'

export function QualityContractBadge({ status, tier, score, lastValidatedAt, isStale, asserted, testCaseCount, regressionPending }: {
  status: string
  tier: string | null
  score: number | null
  lastValidatedAt: string | null
  isStale: boolean
  monitored: boolean
  asserted?: boolean
  testCaseCount?: number | null
  regressionPending?: boolean
}) {
  return <QualityBadge tier={tier} score={score} lastValidatedAt={lastValidatedAt}
    outdated={isStale} asserted={asserted} testCaseCount={testCaseCount}
    regressionPending={regressionPending || status === 'degraded'} />
}
