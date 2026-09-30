import type { TestQuerySnapshot } from '../../api/knowledge'

interface Props {
  snapshot: TestQuerySnapshot | null | undefined
  /** Optional fallback when no snapshot is available (older runs). */
  fallbackQueryCount?: number | null
  /** Compact = single-line chip strip; expanded = multi-line w/ categories. */
  variant?: 'compact' | 'expanded'
}

/**
 * Surfaces the composition of the eval set behind a score — so the user can
 * tell at a glance whether they're looking at "84% on 4 auto-generated
 * questions" vs "84% on 32 hand-curated questions across 6 categories". A
 * raw score with no composition context is the source of most "is this real?"
 * doubts in optimizer UIs.
 */
export function EvalSetCompositionStrip({
  snapshot, fallbackQueryCount, variant = 'compact',
}: Props) {
  if (!snapshot) {
    // Older runs without a snapshot — fall back to bare query count.
    if (fallbackQueryCount == null) return null
    return (
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Chip label={`${fallbackQueryCount} ${fallbackQueryCount === 1 ? 'query' : 'queries'}`} tone="neutral" />
        <Chip label="no composition snapshot" tone="warn" title="This run pre-dates eval-set snapshots, so composition info is unavailable." />
      </div>
    )
  }

  const auto = snapshot.auto_generated_count
  const user = snapshot.user_authored_count
  const total = snapshot.total
  const categoryCount = Object.keys(snapshot.categories || {}).length
  const sourcesCovered = (snapshot.sources_covered || []).length
  const totalSources = snapshot.total_sources
  const coverageRatio = totalSources > 0 ? sourcesCovered / totalSources : null
  const coverageColor =
    coverageRatio == null ? 'neutral'
    : coverageRatio >= 0.8 ? 'good'
    : coverageRatio >= 0.5 ? 'warn'
    : 'bad'
  const autoRatio = total > 0 ? auto / total : 0
  // Heuristic: more than half auto-gen is a credibility signal worth flagging.
  const autoTone: ChipTone = autoRatio > 0.5 ? 'warn' : 'neutral'

  return (
    <div style={{
      display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center',
    }}>
      <Chip
        label={`${total} ${total === 1 ? 'query' : 'queries'}`}
        tone="neutral"
      />
      {(auto > 0 || user > 0) && (
        <Chip
          label={`${auto} auto · ${user} user`}
          tone={autoTone}
          title={autoRatio > 0.5
            ? `${Math.round(autoRatio * 100)}% of the eval set is LLM-generated, so scores may be optimistic if the judge shares assumptions with the generator.`
            : 'Mix of LLM-generated and user-authored test queries.'}
        />
      )}
      {categoryCount > 0 && (
        <Chip
          label={`${categoryCount} ${categoryCount === 1 ? 'category' : 'categories'}`}
          tone="neutral"
          title={Object.entries(snapshot.categories || {})
            .map(([k, v]) => `${k}: ${v}`).join(' · ')}
        />
      )}
      {totalSources > 0 && (
        <Chip
          label={`${sourcesCovered}/${totalSources} sources`}
          tone={coverageColor}
          title={coverageRatio != null
            ? `${Math.round(coverageRatio * 100)}% of KB sources are referenced by at least one test query.`
            : undefined}
        />
      )}
      {variant === 'expanded' && categoryCount > 0 && (
        <div style={{ flexBasis: '100%', marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {Object.entries(snapshot.categories || {}).map(([cat, count]) => (
            <SubChip key={cat} label={`${cat} · ${count}`} />
          ))}
        </div>
      )}
    </div>
  )
}

type ChipTone = 'neutral' | 'good' | 'warn' | 'bad'

const TONE_COLORS: Record<ChipTone, { fg: string; bg: string; border: string }> = {
  neutral: { fg: 'var(--workspace-muted)', bg: 'var(--workspace-canvas)', border: 'var(--workspace-border)' },
  good: { fg: 'var(--workspace-success)', bg: 'rgba(34, 197, 94, 0.08)', border: 'rgba(34, 197, 94, 0.3)' },
  warn: { fg: 'var(--workspace-warning)', bg: 'rgba(245, 158, 11, 0.08)', border: 'rgba(245, 158, 11, 0.3)' },
  bad: { fg: 'var(--workspace-danger)', bg: 'rgba(239, 68, 68, 0.08)', border: 'rgba(239, 68, 68, 0.3)' },
}

function Chip({ label, tone, title }: { label: string; tone: ChipTone; title?: string }) {
  const c = TONE_COLORS[tone]
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex', alignItems: 'center',
        fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        padding: '2px 8px', borderRadius: 6,
        color: c.fg, backgroundColor: c.bg,
        border: `1px solid ${c.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

function SubChip({ label }: { label: string }) {
  return (
    <span style={{
      fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)',
      padding: '1px 6px', borderRadius: 4,
      backgroundColor: 'var(--workspace-canvas)',
      border: '1px solid var(--workspace-border)',
    }}>{label}</span>
  )
}
