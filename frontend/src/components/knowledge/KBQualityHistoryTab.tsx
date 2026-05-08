import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { getKBQuality } from '../../api/knowledge'

interface Props {
  kbUuid: string
}

type HistoryItem = {
  uuid?: string
  score?: number
  grade?: string
  created_at?: string
  num_test_queries?: number
  mode?: string
}

export function KBQualityHistoryTab({ kbUuid }: Props) {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getKBQuality(kbUuid)
      .then(out => setItems((out.history as HistoryItem[]).slice(0, 30)))
      .catch(e => console.error('getKBQuality failed', e))
      .finally(() => setLoading(false))
  }, [kbUuid])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div style={{ fontSize: 12, color: '#888', padding: '20px 0', textAlign: 'center' }}>
        No validation history yet. Run a validation to start tracking quality over time.
      </div>
    )
  }

  // Sparkline: ordered oldest → newest
  const ordered = [...items].reverse()
  const max = Math.max(...ordered.map(i => i.score ?? 0), 100)
  const min = Math.min(...ordered.map(i => i.score ?? 0), 0)

  return (
    <div>
      <div style={{ fontSize: 11, color: '#888', marginBottom: 8 }}>
        Last {ordered.length} runs
      </div>
      {/* Sparkline */}
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 2,
        height: 60, padding: 8, backgroundColor: '#1a1a1a',
        border: '1px solid #2e2e2e', borderRadius: 6, marginBottom: 12,
      }}>
        {ordered.map((it, i) => {
          const score = it.score ?? 0
          const height = max === min ? 50 : ((score - min) / (max - min)) * 100
          const c = scoreColor(score)
          return (
            <div
              key={it.uuid || i}
              title={`${score.toFixed(0)}% — ${it.created_at ?? ''}`}
              style={{
                flex: 1, minWidth: 4,
                height: `${Math.max(4, height)}%`,
                backgroundColor: c,
                borderRadius: 2,
              }}
            />
          )
        })}
      </div>
      {/* Recent runs list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.slice(0, 10).map((it, i) => (
          <div key={it.uuid || i} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '6px 10px', fontSize: 11, color: '#aaa',
            backgroundColor: '#1f1f1f', borderRadius: 4,
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              backgroundColor: scoreColor(it.score ?? 0),
            }} />
            <span style={{ flex: 1 }}>
              {it.created_at ? new Date(it.created_at).toLocaleString() : '—'}
            </span>
            {it.mode && <span style={{ color: '#666' }}>{it.mode}</span>}
            <span style={{ fontWeight: 600, color: '#e5e5e5' }}>
              {(it.score ?? 0).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function scoreColor(s: number) {
  if (s >= 90) return '#22c55e'
  if (s >= 70) return '#3b82f6'
  if (s >= 50) return '#f59e0b'
  return '#ef4444'
}
