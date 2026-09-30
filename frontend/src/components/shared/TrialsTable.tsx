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
  /** Why a trial has no score — shown on hover when `score` is null. */
  error?: string | null
}

/** Score → dot color. Green ≥0.7, amber ≥0.4, red otherwise. */
export function scoreColor(s: number): string {
  if (s >= 0.7) return 'var(--workspace-success)'
  if (s >= 0.4) return 'var(--workspace-warning)'
  return 'var(--workspace-danger)'
}

/**
 * The score/duration sort pair every domain uses. Each domain can extend with
 * its own options if it has extra columns worth sorting by. There's no "Lift"
 * option on purpose: lift_vs_default is score minus a per-run constant, so it
 * would order identically to Score. Duration earns its place because trials
 * are often statistically tied and the fastest tied config is the one to pick.
 */
export function makeStandardSortOptions<T extends StandardTrialFields>(): SortOption<T>[] {
  return [
    { key: 'score', label: 'Score', compare: (a, b) => (b.score ?? 0) - (a.score ?? 0) },
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
  // A null score means the run declined to score this trial (judge
  // coverage below the floor). Rendering it as 0% puts the outage back
  // on screen as a quality collapse — the exact misreport this guards.
  const unscored = trial.score == null
  const score = trial.score ?? 0
  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8,
      padding: '8px 10px', fontSize: 12, color: 'var(--workspace-text)',
      backgroundColor: trial.status === 'failed' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(0,0,0,0.2)',
      borderRadius: 4,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        backgroundColor: unscored ? '#aaa' : scoreColor(score),
      }} />
      <span style={{
        flex: '1 1 160px', minWidth: 0, overflowWrap: 'anywhere', color: 'var(--workspace-text)',
      }}>
        {summariseConfig(trial.config)}
      </span>
      {trial.lift_vs_default != null && (
        <span style={{
          fontSize: 12,
          color: trial.lift_vs_default > 0 ? 'var(--workspace-success)'
            : trial.lift_vs_default < 0 ? 'var(--workspace-danger)' : 'var(--workspace-muted)',
        }}>
          {trial.lift_vs_default > 0 ? '+' : ''}{(trial.lift_vs_default * 100).toFixed(0)}pts
        </span>
      )}
      <span
        title={unscored ? (trial.error || 'Not scored') : undefined}
        style={{
          width: 50, textAlign: 'right', fontWeight: 600,
          color: unscored ? 'var(--workspace-muted)' : 'var(--workspace-text)',
        }}
      >
        {unscored ? '—' : `${(score * 100).toFixed(0)}%`}
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
  /** Optional one-liner under the header — e.g. which eval slice the trial
   * scores were measured on, so they aren't mistaken for the headline score. */
  caption?: ReactNode
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
  caption,
  maxHeight = 320,
  onRowClick,
}: TrialsTableProps<TTrial>) {
  const initialKey = defaultSortKey ?? sortOptions[0]?.key ?? ''
  const [sortKey, setSortKey] = useState<string>(initialKey)
  const sorter = sortOptions.find(o => o.key === sortKey) ?? sortOptions[0]
  const sorted = sorter ? [...trials].sort(sorter.compare) : trials

  return (
    <div style={{
      padding: 14, backgroundColor: 'var(--workspace-surface)',
      border: '1px solid var(--workspace-border)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--workspace-text)' }}>
          {title} ({trials.length})
        </span>
        {sortOptions.length > 1 && (
          <>
            <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--workspace-muted)' }}>Sort by:</span>
            <select
          aria-label="Sort trials"
              value={sortKey}
              onChange={e => setSortKey(e.target.value)}
              style={{
                background: 'var(--workspace-canvas)', color: 'var(--workspace-text)', border: '1px solid var(--workspace-border)',
                borderRadius: 4, padding: '4px 6px', minHeight: 36, maxWidth: '100%', fontSize: 12, fontFamily: 'inherit',
              }}
            >
              {sortOptions.map(o => (
                <option key={o.key} value={o.key}>{o.label}</option>
              ))}
            </select>
          </>
        )}
      </div>
      {caption && (
        <div style={{ marginTop: -6, marginBottom: 10, fontSize: 12, color: 'var(--workspace-muted)', lineHeight: 1.5 }}>
          {caption}
        </div>
      )}
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
