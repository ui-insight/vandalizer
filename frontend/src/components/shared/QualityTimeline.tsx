import { useEffect, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'

/**
 * Generic quality-over-time component used by KB, Extraction, and Workflow
 * surfaces. Each surface supplies a ``fetchHistory`` adapter that returns
 * the normalized ``QualityHistoryItem`` shape — the same shape that
 * ``quality_service.get_quality_history`` already returns for every
 * ``item_kind``.
 *
 * Phase 4 of the loop-closure plan: one timeline, three surfaces. Replaces
 * the per-surface bespoke history tabs so the rendering, judge-model-change
 * warning, CI ribbon, and tooltips don't drift over time.
 */

export interface QualityHistoryItem {
  uuid?: string
  score?: number
  grade?: string | null
  created_at?: string
  num_test_queries?: number
  num_queries_judged?: number
  num_test_cases?: number
  num_checks?: number
  mode?: string
  judge_model?: string | null
  judge_variance?: number | null
  judge_variance_meta?: { sigma: number | null; n: number; sampled_query_uuids?: string[] } | null
  /** Optional source tag — when set to ``"optimizer_apply"`` (Phase 4) the
   *  row renders with a sparkles glyph so users can see that this point
   *  came from an Apply, not a regular validation run. */
  source?: string | null
}

interface Props {
  fetchHistory: () => Promise<{ history: QualityHistoryItem[] }>
  /** Singular noun for what was scored — "KB", "extraction", "workflow". */
  itemKindLabel: string
  /** Plural form used in the empty-state and ITEM_NOUNS labels. */
  itemKindPluralLabel: string
  onSwitchToAutovalidate?: () => void
  /** When provided, used to count sample-size in the row label
   *  (queries / cases / checks). Defaults to "items". */
  sampleNoun?: string
}

export function QualityTimeline({
  fetchHistory, itemKindLabel, itemKindPluralLabel, onSwitchToAutovalidate, sampleNoun = 'items',
}: Props) {
  const [items, setItems] = useState<QualityHistoryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetchHistory()
      .then(out => setItems((out.history || []).slice(0, 30)))
      .catch(e => console.error('QualityTimeline fetchHistory failed', e))
      .finally(() => setLoading(false))
  }, [fetchHistory])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div style={{
        padding: 20, margin: '12px 0',
        background: 'linear-gradient(135deg, #1f1f2e 0%, #1a1a1a 100%)',
        border: '1px solid rgba(124, 58, 237, 0.25)', borderRadius: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Sparkles size={16} style={{ color: '#a78bfa' }} />
          <h3 style={{ margin: 0, fontSize: 14, color: '#fff', fontWeight: 600 }}>
            No quality history yet for this {itemKindLabel}
          </h3>
        </div>
        <p style={{ margin: '0 0 14px 0', fontSize: 13, color: '#bbb', lineHeight: 1.55 }}>
          Each autovalidate or validation run records a quality score here so you can
          watch {itemKindPluralLabel} improve over time. Nothing is mutated until
          you choose to apply a winning configuration.
        </p>
        {onSwitchToAutovalidate && (
          <button
            type="button"
            onClick={onSwitchToAutovalidate}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              color: '#fff',
              background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
              border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
            }}
          >
            <Sparkles size={12} />
            Run autovalidate
          </button>
        )}
      </div>
    )
  }

  const ordered = [...items].reverse()
  const scoreValues = ordered.map(i => i.score ?? 0)
  const max = Math.max(...scoreValues, 100)
  const min = Math.min(...scoreValues, 0)

  const judgeModels = new Set(ordered.map(i => i.judge_model || '').filter(Boolean))
  const judgeModelChanged = judgeModels.size > 1

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: '#888' }}>
          Last {ordered.length} runs
        </div>
        {judgeModelChanged && (
          <span
            title={`Judge model changed across this window: ${[...judgeModels].join(', ')}`}
            style={{
              fontSize: 9, fontWeight: 600,
              padding: '1px 6px', borderRadius: 4,
              color: '#fbbf24', backgroundColor: 'rgba(245, 158, 11, 0.1)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          >
            judge model changed
          </span>
        )}
      </div>
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 2,
        height: 80, padding: 8, backgroundColor: '#1a1a1a',
        border: '1px solid #2e2e2e', borderRadius: 6, marginBottom: 12,
        position: 'relative',
      }}>
        {ordered.map((it, i) => {
          const score = it.score ?? 0
          const heightPct = max === min ? 50 : ((score - min) / (max - min)) * 100
          const c = scoreColor(score)
          const sigmaPts = (it.judge_variance ?? 0) * 100
          const ciHalfPct = max === min ? 0 : ((sigmaPts * 1.96) / (max - min)) * 100
          const titleBits: string[] = []
          titleBits.push(`${score.toFixed(0)}%`)
          if (it.created_at) titleBits.push(new Date(it.created_at).toLocaleString())
          if (it.judge_model) titleBits.push(`judge: ${it.judge_model}`)
          const nq = it.num_queries_judged ?? it.num_test_queries ?? it.num_test_cases ?? it.num_checks
          if (nq != null) titleBits.push(`n=${nq} ${sampleNoun}`)
          if (it.mode) titleBits.push(`mode: ${it.mode}`)
          if (it.source === 'optimizer_apply') titleBits.push('source: optimizer apply')
          if (it.source === 'passive_monthly') titleBits.push('source: monthly auto-re-judge')
          if (sigmaPts > 0) {
            const meta = it.judge_variance_meta
            const provenance = meta?.n ? ` (σ from n=${meta.n})` : ''
            titleBits.push(`±${(sigmaPts * 1.96).toFixed(1)}pts 95% CI${provenance}`)
          }
          const isApply = it.source === 'optimizer_apply'
          return (
            <div
              key={it.uuid || i}
              title={titleBits.join(' · ')}
              style={{
                flex: 1, minWidth: 6, position: 'relative',
                height: `${Math.max(4, heightPct)}%`,
                display: 'flex', flexDirection: 'column-reverse',
              }}
            >
              <div style={{
                width: '100%', height: '100%',
                backgroundColor: c, borderRadius: 2,
                outline: isApply ? '1px solid #a78bfa' : undefined,
              }} />
              {ciHalfPct > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    left: 0, right: 0, bottom: '100%',
                    height: `${Math.min(ciHalfPct, 200)}%`,
                    backgroundColor: c, opacity: 0.18, borderRadius: '2px 2px 0 0',
                    pointerEvents: 'none',
                  }}
                />
              )}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.slice(0, 10).map((it, i) => (
          <Row key={it.uuid || i} item={it} sampleNoun={sampleNoun} />
        ))}
      </div>
    </div>
  )
}

function Row({ item, sampleNoun }: { item: QualityHistoryItem; sampleNoun: string }) {
  const score = item.score ?? 0
  const sigmaPts = (item.judge_variance ?? 0) * 100
  const nq = item.num_queries_judged ?? item.num_test_queries ?? item.num_test_cases ?? item.num_checks
  const isApply = item.source === 'optimizer_apply'
  const isPassive = item.source === 'passive_monthly'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '6px 10px', fontSize: 11, color: '#aaa',
      backgroundColor: '#1f1f1f', borderRadius: 4,
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: '50%',
        backgroundColor: scoreColor(score),
      }} />
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
        {isApply && (
          <span title="Recorded when an optimizer winning config was applied" style={{ marginLeft: 6, color: '#a78bfa' }}>
            · apply
          </span>
        )}
        {isPassive && (
          <span title="Monthly auto-re-judge of the applied tuning — catches quiet regressions after Apply" style={{ marginLeft: 6, color: '#7dd3fc' }}>
            · auto-monthly
          </span>
        )}
      </span>
      {item.judge_model && (
        <span
          title="Judge model"
          style={{
            color: '#666', fontSize: 10,
            maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {item.judge_model}
        </span>
      )}
      {nq != null && <span style={{ color: '#666' }}>n={nq} {sampleNoun}</span>}
      {item.mode && <span style={{ color: '#666' }}>{item.mode}</span>}
      {sigmaPts > 0 && (
        <span title="95% noise-floor band" style={{ color: '#666' }}>
          ±{(sigmaPts * 1.96).toFixed(1)}
        </span>
      )}
      <span style={{ fontWeight: 600, color: '#e5e5e5', minWidth: 38, textAlign: 'right' }}>
        {score.toFixed(0)}%
      </span>
    </div>
  )
}

function scoreColor(s: number) {
  if (s >= 90) return '#22c55e'
  if (s >= 70) return '#3b82f6'
  if (s >= 50) return '#f59e0b'
  return '#ef4444'
}
