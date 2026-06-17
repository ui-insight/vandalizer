import { useCallback, useEffect, useMemo, useState } from 'react'
import { ShieldCheck, Loader2, Sparkles } from 'lucide-react'
import {
  listKBTestQueries,
  getKBQuality,
  type KBTestQuery,
  type KBValidationResult,
} from '../../api/knowledge'
import { AutovalidateTab } from './AutovalidateTab'
import { KBTestQueriesTab } from './KBTestQueriesTab'
import { KBValidationRunTab } from './KBValidationRunTab'
import { KBQualityHistoryTab } from './KBQualityHistoryTab'

type Tab = 'autovalidate' | 'queries' | 'run' | 'history'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
}

const TAB_LABELS: { id: Tab; label: string; icon?: typeof Sparkles }[] = [
  { id: 'autovalidate', label: 'Tune', icon: Sparkles },
  { id: 'queries', label: 'Test Queries' },
  { id: 'run', label: 'Run now' },
  { id: 'history', label: 'History' },
]

/** Provenance summary for the score chip in the validation header. We surface
 * judge model, eval-set size, mode, and age so users can tell whether the
 * "85" they see is fresh, on a comparable judge, and on a comparable set —
 * which addresses the audit's "no labeling, no reconciliation" gap. */
type LatestQualitySummary = {
  score: number
  judgeModel: string | null
  numQueries: number | null
  mode: string | null
  createdAt: string | null
}

export function KBValidationPanel({ kbUuid, kbReady, canManage }: Props) {
  const [tab, setTab] = useState<Tab>('autovalidate')
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [latestRun, setLatestRun] = useState<KBValidationResult | null>(null)
  const [latestQuality, setLatestQuality] = useState<LatestQualitySummary | null>(null)
  const [loading, setLoading] = useState(false)

  const refreshQueries = useCallback(async () => {
    try {
      const out = await listKBTestQueries(kbUuid)
      setQueries(out.test_queries)
    } catch (e) {
      console.error('listKBTestQueries failed', e)
    }
  }, [kbUuid])

  const refreshHistory = useCallback(async () => {
    try {
      const out = await getKBQuality(kbUuid)
      const history = (out.history as Array<{
        score?: number
        judge_model?: string | null
        num_queries_judged?: number | null
        num_test_queries?: number | null
        mode?: string | null
        created_at?: string | null
      }>)
      const last = history[0]
      setLatestQuality(last?.score != null ? {
        score: Number(last.score),
        judgeModel: last.judge_model ?? null,
        numQueries: last.num_queries_judged ?? last.num_test_queries ?? null,
        mode: last.mode ?? null,
        createdAt: last.created_at ?? null,
      } : null)
    } catch (e) {
      console.error('getKBQuality failed', e)
    }
  }, [kbUuid])

  useEffect(() => {
    setLoading(true)
    Promise.all([refreshQueries(), refreshHistory()]).finally(() => setLoading(false))
  }, [refreshQueries, refreshHistory])

  const latestScore = latestQuality?.score ?? null
  const scoreColor =
    latestScore == null ? '#666'
    : latestScore >= 90 ? '#22c55e'
    : latestScore >= 70 ? '#3b82f6'
    : latestScore >= 50 ? '#f59e0b'
    : '#ef4444'

  // Build the "source of this score" tooltip — answers the audit's #11 directly.
  const tooltip = useMemo(() => {
    if (!latestQuality) return undefined
    const parts: string[] = []
    parts.push(`Score: ${latestQuality.score.toFixed(0)}`)
    if (latestQuality.judgeModel) parts.push(`judged by ${latestQuality.judgeModel}`)
    if (latestQuality.numQueries != null) parts.push(`on ${latestQuality.numQueries} queries`)
    if (latestQuality.mode) parts.push(`(${latestQuality.mode})`)
    if (latestQuality.createdAt) {
      const when = new Date(latestQuality.createdAt)
      parts.push(`at ${when.toLocaleString()}`)
    }
    return parts.join(' · ')
  }, [latestQuality])

  // Inline provenance line shown next to the score chip — keeps the score's
  // meaning visible without forcing a hover.
  const provenance = latestQuality
    ? [
        latestQuality.judgeModel && shortenModel(latestQuality.judgeModel),
        latestQuality.numQueries != null ? `n=${latestQuality.numQueries}` : null,
        latestQuality.createdAt ? relativeTime(latestQuality.createdAt) : null,
      ].filter(Boolean).join(' · ')
    : null

  return (
    <div
      style={{
        marginTop: 16,
        padding: 12,
        backgroundColor: '#1f1f1f',
        border: '1px solid #2e2e2e',
        borderRadius: 8,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <ShieldCheck size={16} style={{ color: '#7d8590' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5' }}>Validation</span>
        {latestScore != null && (
          <span
            title={tooltip}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
              color: scoreColor, backgroundColor: 'rgba(255,255,255,0.05)',
              border: `1px solid ${scoreColor}33`,
            }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%', backgroundColor: scoreColor,
            }} />
            {latestScore.toFixed(0)}
          </span>
        )}
        {provenance && (
          <span
            title={tooltip}
            style={{
              fontSize: 10, color: '#666',
              maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {provenance}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>
          {queries.length} {queries.length === 1 ? 'query' : 'queries'}
        </span>
      </div>

      {/* Orientation hint — single sentence above the tab strip so new users
          know what each tab is for without clicking through. */}
      <div
        style={{
          fontSize: 11, color: '#888', marginBottom: 6, lineHeight: 1.5,
        }}
      >
        <b style={{ color: '#bbb' }}>Tune</b> to improve. <b style={{ color: '#bbb' }}>Run now</b> to spot-check.{' '}
        <b style={{ color: '#bbb' }}>Test Queries</b> are the rubric.
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid #2e2e2e', marginBottom: 10 }}>
        {TAB_LABELS.map(t => {
          const active = tab === t.id
          const Icon = t.icon
          const isAuto = t.id === 'autovalidate'
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                fontFamily: 'inherit',
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'transparent',
                color: active ? '#fff' : '#888',
                border: 'none',
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                borderBottom: active
                  ? `2px solid ${isAuto ? '#a78bfa' : '#2563eb'}`
                  : '2px solid transparent',
                marginBottom: -1,
              }}
            >
              {Icon && <Icon size={12} style={{ color: active ? (isAuto ? '#a78bfa' : '#fff') : '#888' }} />}
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
          <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      ) : tab === 'autovalidate' ? (
        <AutovalidateTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          queriesCount={queries.length}
          onSwitchToQueries={() => setTab('queries')}
        />
      ) : tab === 'queries' ? (
        <KBTestQueriesTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          queries={queries}
          onChange={refreshQueries}
        />
      ) : tab === 'run' ? (
        <KBValidationRunTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          numQueries={queries.length}
          latestRun={latestRun}
          onRun={(r) => { setLatestRun(r); refreshHistory() }}
        />
      ) : (
        <KBQualityHistoryTab kbUuid={kbUuid} onSwitchToAutovalidate={() => setTab('autovalidate')} />
      )}
    </div>
  )
}

/** Compact model identifier — drop provider prefix and version dates so the
 * provenance string stays readable in the header. */
function shortenModel(name: string): string {
  const noProvider = name.split('/').pop() ?? name
  const noDate = noProvider.replace(/-\d{4}-\d{2}-\d{2}$/, '')
  return noDate.length > 24 ? noDate.slice(0, 22) + '…' : noDate
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 90) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 90) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 36) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 14) return `${days}d ago`
  const weeks = Math.round(days / 7)
  return `${weeks}w ago`
}
