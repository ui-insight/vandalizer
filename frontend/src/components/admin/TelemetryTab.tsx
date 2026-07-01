import { useCallback, useEffect, useState } from 'react'
import {
  Globe, Activity, Tag, EyeOff, RefreshCw, Server,
} from 'lucide-react'

import { getTelemetryAnalytics, type TelemetryAnalytics } from '../../api/admin'
import { relativeTime } from '../../utils/time'

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Tag
  label: string
  value: string | number
  color: string
}) {
  return (
    <div style={{
      flex: 1, minWidth: 160,
      backgroundColor: '#fff', border: '1px solid #e5e7eb',
      borderRadius: 8, padding: 16,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#6b7280', fontSize: 13 }}>
        <Icon size={16} color={color} />
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{value}</div>
    </div>
  )
}

// A simple labeled distribution: sorted desc, bar width relative to the max.
function Distribution({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1])
  const max = entries.reduce((m, [, n]) => Math.max(m, n), 0) || 1
  return (
    <div style={{
      flex: 1, minWidth: 240,
      backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>{title}</div>
      {entries.length === 0 ? (
        <div style={{ fontSize: 13, color: '#6b7280' }}>No data yet</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.map(([key, n]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 90, fontSize: 12, color: '#6b7280', textAlign: 'right', flexShrink: 0 }}>{key}</div>
              <div style={{ flex: 1, height: 18, backgroundColor: '#f3f4f6', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: `${(n / max) * 100}%`, height: '100%', backgroundColor: '#6366f1', borderRadius: 4 }} />
              </div>
              <div style={{ width: 32, fontSize: 12, fontWeight: 600, color: '#111827', textAlign: 'right' }}>{n}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function TelemetryTab() {
  const [data, setData] = useState<TelemetryAnalytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getTelemetryAnalytics())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load telemetry')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  if (loading && !data) {
    return <div style={{ padding: 24, color: '#6b7280' }}>Loading…</div>
  }
  if (error) {
    return <div style={{ padding: 24, color: '#dc2626' }}>{error}</div>
  }
  if (!data) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Fleet Telemetry</h2>
          <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0 0' }}>
            Anonymous heartbeats from deployments that opted in. Counts are coarse buckets; identity appears only where a deployment self-declared it.
          </p>
        </div>
        <button
          onClick={() => void reload()}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 12px', fontSize: 13, fontWeight: 500,
            backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
            color: '#374151', cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <StatCard icon={Globe} label="Total deployments" value={data.total_instances} color="#6366f1" />
        <StatCard icon={Activity} label="Active (30d)" value={data.active_instances_30d} color="#22c55e" />
        <StatCard icon={Tag} label="Named" value={data.named_instances} color="#3b82f6" />
        <StatCard icon={EyeOff} label="Anonymous" value={data.anonymous_instances} color="#9ca3af" />
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Distribution title="By version (active)" data={data.by_version} />
        <Distribution title="By environment (active)" data={data.by_environment} />
        <Distribution title="Users per deployment (active)" data={data.users_buckets} />
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderBottom: '1px solid #f3f4f6' }}>
          <Server size={16} color="#6b7280" />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
            Named deployments ({data.named_deployments.length})
          </span>
        </div>
        {data.named_deployments.length === 0 ? (
          <div style={{ padding: 24, fontSize: 13, color: '#6b7280' }}>
            No deployments have self-identified yet.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: '#6b7280' }}>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Organization</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Version</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Environment</th>
                <th scope="col" style={{ padding: '8px 16px', fontWeight: 500 }}>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {data.named_deployments.map((d, i) => (
                <tr key={`${d.organization}-${i}`} style={{ borderTop: '1px solid #f3f4f6', opacity: d.active ? 1 : 0.5 }}>
                  <td style={{ padding: '8px 16px', fontWeight: 600, color: '#111827' }}>{d.organization}</td>
                  <td style={{ padding: '8px 16px', color: '#374151' }}>{d.version}</td>
                  <td style={{ padding: '8px 16px', color: '#374151' }}>{d.environment}</td>
                  <td style={{ padding: '8px 16px', color: '#6b7280' }}>{relativeTime(d.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
