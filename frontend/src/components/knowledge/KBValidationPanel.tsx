import { useCallback, useEffect, useState } from 'react'
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
  { id: 'autovalidate', label: 'Autovalidate', icon: Sparkles },
  { id: 'queries', label: 'Test Queries' },
  { id: 'run', label: 'Manual Run' },
  { id: 'history', label: 'History' },
]

export function KBValidationPanel({ kbUuid, kbReady, canManage }: Props) {
  const [tab, setTab] = useState<Tab>('autovalidate')
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [latestRun, setLatestRun] = useState<KBValidationResult | null>(null)
  const [latestScore, setLatestScore] = useState<number | null>(null)
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
      const last = (out.history as Array<{ score?: number }>)[0]
      setLatestScore(last?.score != null ? Number(last.score) : null)
    } catch (e) {
      console.error('getKBQuality failed', e)
    }
  }, [kbUuid])

  useEffect(() => {
    setLoading(true)
    Promise.all([refreshQueries(), refreshHistory()]).finally(() => setLoading(false))
  }, [refreshQueries, refreshHistory])

  const scoreColor =
    latestScore == null ? '#666'
    : latestScore >= 90 ? '#22c55e'
    : latestScore >= 70 ? '#3b82f6'
    : latestScore >= 50 ? '#f59e0b'
    : '#ef4444'

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
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
            color: scoreColor, backgroundColor: 'rgba(255,255,255,0.05)',
            border: `1px solid ${scoreColor}33`,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', backgroundColor: scoreColor,
            }} />
            {latestScore.toFixed(0)}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>
          {queries.length} {queries.length === 1 ? 'query' : 'queries'}
        </span>
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
        <AutovalidateTab kbUuid={kbUuid} kbReady={kbReady} canManage={canManage} />
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
        <KBQualityHistoryTab kbUuid={kbUuid} />
      )}
    </div>
  )
}
