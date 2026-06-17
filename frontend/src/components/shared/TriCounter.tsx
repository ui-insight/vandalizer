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
      <div style={{ fontSize: 11, color: '#666', padding: '6px 0' }}>
        Per-query comparison unavailable for this run.
      </div>
    )
  }

  const { improved, regressed, unchanged, biggestRegression } = counts

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 12px',
      backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e',
      borderRadius: 8,
    }}>
      <Counter
        icon={<ArrowUpRight size={14} />}
        value={improved}
        label="improved"
        color="#22c55e"
      />
      <Counter
        icon={<ArrowDownRight size={14} />}
        value={regressed}
        label="regressed"
        color={regressed > 0 ? '#ef4444' : '#666'}
      />
      <Counter
        icon={<Minus size={14} />}
        value={unchanged}
        label="unchanged"
        color="#888"
      />
      {biggestRegression && (
        <div style={{
          marginLeft: 'auto', fontSize: 10, color: '#fca5a5',
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
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ color }}>{icon}</span>
      <span style={{ fontSize: 18, fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: 11, color: '#888' }}>{label}</span>
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
