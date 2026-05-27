import { useMemo, useState } from 'react'
import { ArrowUpRight, ArrowDownRight } from 'lucide-react'
import type { PerQueryResult } from '../../api/knowledge'
import { TraceDrawer } from './TraceDrawer'
import { scoreColor } from './TrialsTable'

interface Props {
  /** The winning trial's per-query results. */
  optimized: PerQueryResult[] | undefined
  /** The default-config baseline's per-query results. */
  baseline: PerQueryResult[] | undefined
  /** Optional no-KB baseline — shown in trace drawer when available. */
  noKb?: PerQueryResult[] | undefined
  title?: string
}

type SortKey = 'delta-desc' | 'delta-asc' | 'optimized-desc' | 'optimized-asc'

/**
 * Per-query delta table for the optimizer winner: every query, baseline → optimized,
 * sortable by biggest wins / biggest regressions. Click a row to see the full
 * trace. This is the W&B / Braintrust pattern that lets a user audit whether
 * the headline lift is broad-based or a single-query swing.
 */
export function TrialQueryDeltas({
  optimized, baseline, noKb, title = 'Per-query deltas',
}: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('delta-desc')
  const [drawerFor, setDrawerFor] = useState<string | null>(null)

  const baseByUuid = useMemo(() => new Map((baseline || []).map(r => [r.query_uuid, r])), [baseline])
  const noKbByUuid = useMemo(() => new Map((noKb || []).map(r => [r.query_uuid, r])), [noKb])

  const rows = useMemo(() => {
    if (!optimized) return []
    const out = optimized.map(o => {
      const base = baseByUuid.get(o.query_uuid)
      const delta = base ? o.score - base.score : null
      return { optimized: o, baseline: base, delta }
    })
    const cmp = (a: typeof out[number], b: typeof out[number]) => {
      switch (sortKey) {
        case 'delta-desc': return (b.delta ?? -Infinity) - (a.delta ?? -Infinity)
        case 'delta-asc':  return (a.delta ?? Infinity) - (b.delta ?? Infinity)
        case 'optimized-desc': return b.optimized.score - a.optimized.score
        case 'optimized-asc':  return a.optimized.score - b.optimized.score
      }
    }
    return [...out].sort(cmp)
  }, [optimized, baseByUuid, sortKey])

  if (!optimized || optimized.length === 0) {
    return (
      <div style={{
        padding: 12, fontSize: 12, color: '#888',
        backgroundColor: '#1f1f1f', border: '1px solid #2e2e2e', borderRadius: 8,
      }}>
        Per-query data isn't available for this run.
      </div>
    )
  }

  const drawerRow = drawerFor
    ? rows.find(r => r.optimized.query_uuid === drawerFor)
    : null

  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
          {title} ({rows.length})
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#666' }}>Sort by:</span>
        <select
          value={sortKey}
          onChange={e => setSortKey(e.target.value as SortKey)}
          style={{
            background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
            borderRadius: 4, padding: '2px 6px', fontSize: 11, fontFamily: 'inherit',
          }}
        >
          <option value="delta-desc">Biggest wins</option>
          <option value="delta-asc">Biggest regressions</option>
          <option value="optimized-desc">Optimized score (high→low)</option>
          <option value="optimized-asc">Optimized score (low→high)</option>
        </select>
      </div>

      <div style={{
        display: 'flex', flexDirection: 'column', gap: 3,
        maxHeight: 360, overflowY: 'auto',
      }}>
        <HeaderRow />
        {rows.map(({ optimized: o, baseline: b, delta }) => (
          <Row
            key={o.query_uuid}
            optimized={o}
            baseline={b}
            delta={delta}
            onOpen={() => setDrawerFor(o.query_uuid)}
          />
        ))}
      </div>

      <TraceDrawer
        open={drawerFor != null}
        onClose={() => setDrawerFor(null)}
        optimized={drawerRow?.optimized ?? null}
        baseline={drawerRow?.baseline ?? null}
        noKb={drawerRow ? noKbByUuid.get(drawerRow.optimized.query_uuid) ?? null : null}
      />
    </div>
  )
}

function HeaderRow() {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 60px 60px 70px',
      gap: 6, padding: '4px 8px',
      fontSize: 9, color: '#666',
      textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      <span>Query</span>
      <span style={{ textAlign: 'right' }}>Default</span>
      <span style={{ textAlign: 'right' }}>Optimized</span>
      <span style={{ textAlign: 'right' }}>Δ</span>
    </div>
  )
}

function Row({
  optimized, baseline, delta, onOpen,
}: {
  optimized: PerQueryResult
  baseline?: PerQueryResult
  delta: number | null
  onOpen: () => void
}) {
  const oScore = optimized.score
  const bScore = baseline?.score ?? null
  const deltaPts = delta != null ? delta * 100 : null
  const deltaColor =
    deltaPts == null ? '#666'
    : deltaPts > 5 ? '#22c55e'
    : deltaPts < -5 ? '#ef4444'
    : '#888'

  return (
    <button
      onClick={onOpen}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 60px 60px 70px',
        gap: 6, padding: '6px 8px',
        fontSize: 11, color: '#ddd',
        backgroundColor: '#1a1a1a',
        border: '1px solid #262626',
        borderRadius: 4, cursor: 'pointer',
        textAlign: 'left', fontFamily: 'inherit',
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = '#3a3a3a')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '#262626')}
      title={optimized.query}
    >
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#ddd' }}>
        {optimized.query}
      </span>
      <span style={{ textAlign: 'right', color: bScore != null ? scoreColor(bScore) : '#444' }}>
        {bScore != null ? `${(bScore * 100).toFixed(0)}%` : '—'}
      </span>
      <span style={{ textAlign: 'right', color: scoreColor(oScore), fontWeight: 600 }}>
        {(oScore * 100).toFixed(0)}%
      </span>
      <span style={{
        textAlign: 'right', color: deltaColor, fontWeight: 600,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'flex-end', gap: 2,
      }}>
        {deltaPts == null ? '—' : (
          <>
            {deltaPts > 5 ? <ArrowUpRight size={10} /> : deltaPts < -5 ? <ArrowDownRight size={10} /> : null}
            {deltaPts > 0 ? '+' : ''}{deltaPts.toFixed(0)}
          </>
        )}
      </span>
    </button>
  )
}

