import { useState } from 'react'
import type { ReactNode } from 'react'

export interface SortOption<TTrial> {
  key: string
  label: string
  /** Comparator passed to Array.sort; return negative if a should come first. */
  compare: (a: TTrial, b: TTrial) => number
}

/**
 * Fields every domain's trial type shares, used by the standard sort options
 * and the standard row renderer. KB and extraction both populate these; a
 * future workflow trial would too.
 */
export interface StandardTrialFields {
  score?: number | null
  lift_vs_default?: number | null
  duration_seconds?: number | null
  status?: string
}

/** Score → dot color. Green ≥0.7, amber ≥0.4, red otherwise. */
export function scoreColor(s: number): string {
  if (s >= 0.7) return '#22c55e'
  if (s >= 0.4) return '#f59e0b'
  return '#ef4444'
}

/**
 * The score/lift/duration sort triad both KB and extraction use. Each domain
 * can extend with its own options if it has extra columns worth sorting by.
 */
export function makeStandardSortOptions<T extends StandardTrialFields>(): SortOption<T>[] {
  return [
    { key: 'score', label: 'Score', compare: (a, b) => (b.score ?? 0) - (a.score ?? 0) },
    { key: 'lift', label: 'Lift', compare: (a, b) => (b.lift_vs_default ?? 0) - (a.lift_vs_default ?? 0) },
    { key: 'duration', label: 'Duration', compare: (a, b) => (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0) },
  ]
}

/**
 * Standard trial-row layout: score dot · config summary · lift delta · score %.
 *
 * Domain consumers pass a `summariseConfig` callback to format their config
 * shape — that's the only domain-specific bit. Everything else (layout,
 * colors, padding, lift sign coloring) is identical across domains.
 */
export function TrialRow<TConfig>({
  trial, summariseConfig,
}: {
  trial: StandardTrialFields & { config: TConfig }
  summariseConfig: (config: TConfig) => string
}) {
  const score = trial.score ?? 0
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 10px', fontSize: 11, color: '#ddd',
      backgroundColor: trial.status === 'failed' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(0,0,0,0.2)',
      borderRadius: 4,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        backgroundColor: scoreColor(score),
      }} />
      <span style={{
        flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
        whiteSpace: 'nowrap', color: '#aaa',
      }}>
        {summariseConfig(trial.config)}
      </span>
      {trial.lift_vs_default != null && (
        <span style={{
          fontSize: 10,
          color: trial.lift_vs_default > 0 ? '#22c55e'
            : trial.lift_vs_default < 0 ? '#ef4444' : '#666',
        }}>
          {trial.lift_vs_default > 0 ? '+' : ''}{(trial.lift_vs_default * 100).toFixed(0)}pts
        </span>
      )}
      <span style={{
        width: 50, textAlign: 'right', fontWeight: 600, color: '#e5e5e5',
      }}>
        {(score * 100).toFixed(0)}%
      </span>
    </div>
  )
}

interface TrialsTableProps<TTrial> {
  trials: TTrial[]
  sortOptions: SortOption<TTrial>[]
  /** Sort key to use initially. Defaults to the first sort option. */
  defaultSortKey?: string
  /** Domain-specific row renderer. Caller controls full row layout. */
  renderRow: (trial: TTrial) => ReactNode
  getRowKey: (trial: TTrial) => string
  title?: string
  maxHeight?: number | string
  /** When provided, rows become clickable (pointer cursor + hover + keyboard)
   * and invoke this with the clicked trial. Omit for a static, read-only list. */
  onRowClick?: (trial: TTrial) => void
}

/**
 * Generic scrollable list of optimization trials with a sort-by dropdown.
 *
 * Each domain (KB / extraction / workflow) provides its own row renderer and
 * sort options; the component only owns the chrome (header, dropdown, scroll
 * container) and the sort state.
 */
export function TrialsTable<TTrial>({
  trials, sortOptions,
  defaultSortKey,
  renderRow, getRowKey,
  title = 'Trials',
  maxHeight = 320,
  onRowClick,
}: TrialsTableProps<TTrial>) {
  const initialKey = defaultSortKey ?? sortOptions[0]?.key ?? ''
  const [sortKey, setSortKey] = useState<string>(initialKey)
  const sorter = sortOptions.find(o => o.key === sortKey) ?? sortOptions[0]
  const sorted = sorter ? [...trials].sort(sorter.compare) : trials

  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
          {title} ({trials.length})
        </span>
        {sortOptions.length > 1 && (
          <>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: '#666' }}>Sort by:</span>
            <select
              value={sortKey}
              onChange={e => setSortKey(e.target.value)}
              style={{
                background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
                borderRadius: 4, padding: '2px 6px', fontSize: 11, fontFamily: 'inherit',
              }}
            >
              {sortOptions.map(o => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>
          </>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight, overflowY: 'auto' }}>
        {sorted.map(t => (
          onRowClick ? (
            <ClickableRow key={getRowKey(t)} onClick={() => onRowClick(t)}>
              {renderRow(t)}
            </ClickableRow>
          ) : (
            <div key={getRowKey(t)}>
              {renderRow(t)}
            </div>
          )
        ))}
      </div>
    </div>
  )
}

/** Row wrapper that adds click + keyboard activation and a hover affordance.
 * Used only when the table is given an onRowClick. */
function ClickableRow({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        cursor: 'pointer',
        borderRadius: 4,
        outline: hover ? '1px solid #3a3a3a' : '1px solid transparent',
        transition: 'outline-color 0.12s',
      }}
      title="View what this trial tried and why it matters"
    >
      {children}
    </div>
  )
}
