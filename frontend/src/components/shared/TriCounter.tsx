import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import type { PerQueryResult } from '../../api/knowledge'

interface Props {
  optimized: PerQueryResult[] | undefined
  baseline: PerQueryResult[] | undefined
  /** Indifference band — deltas within ±epsilon are "unchanged". Default 0.05
   * matches the backend's PER_QUERY_DELTA_EPSILON. */
  epsilon?: number
}

/**
 * "M improved · K regressed · U unchanged" — the answer to "did we trade one
 * weakness for another?". Without this view, a +13pt lift could be a broad
 * improvement or a single-query swing masking N regressions.
 */
export function TriCounter({ optimized, baseline, epsilon = 0.05 }: Props) {
  const counts = computeCounts(optimized || [], baseline || [], epsilon)
  if (counts == null) {
    return (
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', padding: "var(--workspace-space-6) 0" }}>
        Per-query comparison unavailable for this run.
      </div>
    )
  }

  const { improved, regressed, unchanged, biggestRegression } = counts

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)',
      padding: "var(--workspace-space-12) var(--workspace-space-12)",
      backgroundColor: 'var(--workspace-surface)',
      border: '1px solid var(--workspace-border)',
      borderRadius: 'var(--workspace-radius-medium)',
    }}>
      <Counter
        icon={<ArrowUpRight size={14} />}
        value={improved}
        label="improved"
        color="var(--workspace-success)"
      />
      <Counter
        icon={<ArrowDownRight size={14} />}
        value={regressed}
        label="regressed"
        color={regressed > 0 ? 'var(--workspace-danger)' : 'var(--workspace-muted)'}
      />
      <Counter
        icon={<Minus size={14} />}
        value={unchanged}
        label="unchanged"
        color="var(--workspace-muted)"
      />
      {biggestRegression && (
        <div style={{
          marginLeft: 'auto', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)',
          maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
          title={`Biggest regression: "${biggestRegression.query}" ${(biggestRegression.before*100).toFixed(0)}% → ${(biggestRegression.after*100).toFixed(0)}%`}
        >
          ⚠ biggest drop: {biggestRegression.before === 0 ? '' : `${(biggestRegression.before*100).toFixed(0)}% → `}
          {(biggestRegression.after*100).toFixed(0)}%
        </div>
      )}
    </div>
  )
}

function Counter({
  icon, value, label, color,
}: { icon: React.ReactNode; value: number; label: string; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)' }}>
      <span style={{ color }}>{icon}</span>
      <span style={{ fontSize: 'var(--workspace-font-section-title)', fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>{label}</span>
    </div>
  )
}

function computeCounts(
  optimized: PerQueryResult[],
  baseline: PerQueryResult[],
  epsilon: number,
) {
  if (optimized.length === 0 || baseline.length === 0) return null
  const byUuid = new Map(baseline.map(r => [r.query_uuid, r.score]))
  let improved = 0
  let regressed = 0
  let unchanged = 0
  let biggestRegression: { query: string; before: number; after: number; delta: number } | null = null
  for (const o of optimized) {
    const baseScore = byUuid.get(o.query_uuid)
    if (baseScore == null) continue
    const delta = o.score - baseScore
    if (delta > epsilon) improved += 1
    else if (delta < -epsilon) {
      regressed += 1
      if (!biggestRegression || delta < biggestRegression.delta) {
        biggestRegression = { query: o.query, before: baseScore, after: o.score, delta }
      }
    } else unchanged += 1
  }
  if (improved + regressed + unchanged === 0) return null
  return { improved, regressed, unchanged, biggestRegression }
}
