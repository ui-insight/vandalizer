import { useAdminViewState } from './shared/AdminViewState'
import { useCallback } from 'react'
import {
  Send, XCircle, CheckCircle2, AlertCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend,
} from 'recharts'
import { getEmailAnalytics } from '../../api/admin'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import { downloadCSV, formatDateTime, formatNumber } from './shared/format'
import {
  KpiCard, ExportButton, TimeRangeSelector,
} from './shared/primitives'

export function EmailAnalyticsTab() {
  const [days, setDays] = useAdminViewState('EmailAnalyticsTab.days', 30)
  const request = useCallback(() => getEmailAnalytics(days), [days])
  const { data, loading, error, load } = useAdminQuery(request)

  if (loading && !data) {
    return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading email analytics...</div>
  }
  if (error && !data) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
        <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
        <div role="alert" style={{ fontSize: 14, color: '#991b1b' }}>{error} <button onClick={load} style={{ textDecoration: 'underline' }}>Retry email analytics</button></div>
      </div>
    )
  }
  if (!data) return null

  const successPct = (data.success_rate * 100).toFixed(1)
  const overallHealthColor =
    data.total_sent + data.total_failed === 0 ? '#6b7280'
    : data.success_rate >= 0.99 ? '#15803d'
    : data.success_rate >= 0.9 ? '#92400e' : '#b91c1c'

  const handleExport = () => {
    const dailyRows = data.by_day.map(p => [p.date, p.sent, p.failed])
    const typeRows = data.by_type.map(t => [t.email_type, t.sent, t.failed, (t.success_rate * 100).toFixed(2) + '%'])
    const failureRows = data.recent_failures.map(f => [f.created_at, f.recipient, f.email_type, f.provider, f.subject, f.error || ''])
    downloadCSV(
      `email-analytics-${days}d.csv`,
      ['Section', 'A', 'B', 'C', 'D', 'E'],
      [
        ['SUMMARY', '', '', '', '', ''],
        ['Window (days)', days, '', '', '', ''],
        ['Total Sent', data.total_sent, '', '', '', ''],
        ['Total Failed', data.total_failed, '', '', '', ''],
        ['Success Rate', (data.success_rate * 100).toFixed(2) + '%', '', '', '', ''],
        ['Providers', data.providers.join('; '), '', '', '', ''],
        ['', '', '', '', '', ''],
        ['DAILY', 'Date', 'Sent', 'Failed', '', ''],
        ...dailyRows.map(r => ['', ...r, '', '']),
        ['', '', '', '', '', ''],
        ['BY TYPE', 'Type', 'Sent', 'Failed', 'Success Rate', ''],
        ...typeRows.map(r => ['', ...r, '']),
        ['', '', '', '', '', ''],
        ['RECENT FAILURES', 'When', 'Recipient', 'Type', 'Provider', 'Error'],
        ...failureRows.map(r => ['', r[0], r[1], r[2], r[3], `${r[4]}: ${r[5]}`]),
      ],
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', borderRadius: 'var(--ui-radius, 12px)',
          background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontSize: 13,
        }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <TimeRangeSelector value={days} onChange={v => setDays(typeof v === 'number' ? v : 30)} onRefresh={load} />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={handleExport} />
        {data.providers.length > 0 && (
          <span style={{ fontSize: 12, color: '#6b7280', width: '100%', textAlign: 'right' }}>
            Provider{data.providers.length > 1 ? 's' : ''}: {data.providers.join(', ')}
          </span>
        )}
      </div>

      <p style={{ margin: 0, fontSize: 13, color: '#4b5563', lineHeight: 1.6 }}>
        Last {days} days. Sent means the provider accepted the send request; it does not confirm inbox delivery or that a message was read.
        {' '}Success rate is sent requests divided by sent plus failed requests. Daily buckets use UTC; failure timestamps use your local timezone.
        {' '}Export includes this period’s summary, daily counts, types, and the loaded recent failures.
      </p>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 180px), 1fr))', gap: 16 }}>
        <KpiCard label="Sent" value={formatNumber(data.total_sent)} icon={Send} color="#15803d" />
        <KpiCard label="Failed" value={formatNumber(data.total_failed)} icon={XCircle} color="#b91c1c" />
        <KpiCard label="Success Rate" value={`${successPct}%`} icon={CheckCircle2} color={overallHealthColor} />
      </div>

      {/* Daily chart */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Daily Email Volume</div>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={data.by_day}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} tickFormatter={v => v.slice(5)} />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} width={40} allowDecimals={false} />
            <Tooltip contentStyle={{ borderRadius: 8, fontSize: 13, border: '1px solid #e5e7eb' }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area type="monotone" dataKey="sent" stackId="1" stroke="#15803d" fill="#15803d" fillOpacity={0.2} name="Sent" />
            <Area type="monotone" dataKey="failed" stackId="1" stroke="#b91c1c" fill="#b91c1c" fillOpacity={0.25} name="Failed" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* By type */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ fontSize: 15, fontWeight: 600, padding: '16px 20px', borderBottom: '1px solid #f3f4f6' }}>
          By Email Type
        </div>
        {data.by_type.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280', fontSize: 13 }}>
            No emails sent in this window.
          </div>
        ) : (
          <TableRegion label="Email counts by type"><table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: '#fafafa' }}>
              <tr>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Type</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Sent</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Failed</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {data.by_type.map(row => {
                const rate = row.success_rate * 100
                const color = row.sent + row.failed === 0 ? '#6b7280'
                  : row.success_rate >= 0.99 ? '#15803d'
                  : row.success_rate >= 0.9 ? '#92400e' : '#b91c1c'
                return (
                  <tr key={row.email_type} style={{ borderTop: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px', fontSize: 13, color: '#111827' }}>{row.email_type}</td>
                    <td style={{ padding: '10px 16px', fontSize: 13, textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>{row.sent}</td>
                    <td style={{ padding: '10px 16px', fontSize: 13, textAlign: 'right', fontFamily: 'ui-monospace, monospace', color: row.failed > 0 ? '#b91c1c' : '#6b7280' }}>{row.failed}</td>
                    <td style={{ padding: '10px 16px', fontSize: 13, textAlign: 'right', fontFamily: 'ui-monospace, monospace', color, fontWeight: 600 }}>{rate.toFixed(1)}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table></TableRegion>
        )}
      </div>

      {/* Recent failures */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ fontSize: 15, fontWeight: 600, padding: '16px 20px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={16} color="#b91c1c" /> Recent Failures
        </div>
        {data.recent_failures.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280', fontSize: 13 }}>
            No recorded failures in this window.
          </div>
        ) : (
          <TableRegion label="Recent email failures"><table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: '#fafafa' }}>
              <tr>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>When</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Recipient</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Type</th>
                <th scope="col" style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_failures.map((f, i) => (
                <tr key={i} style={{ borderTop: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap' }}>{formatDateTime(f.created_at)}</td>
                  <td style={{ padding: '10px 16px', fontSize: 13, color: '#111827', fontFamily: 'ui-monospace, monospace' }}>{f.recipient}</td>
                  <td style={{ padding: '10px 16px', fontSize: 13, color: '#374151' }}>{f.email_type}</td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: '#b91c1c', maxWidth: 420, overflowWrap: 'anywhere' }}>
                    <details>
                      <summary style={{ cursor: 'pointer' }}>View failure details</summary>
                      <dl>
                        <dt>Provider</dt><dd>{f.provider || 'Not recorded'}</dd>
                        <dt>Subject</dt><dd>{f.subject || 'Not recorded'}</dd>
                        <dt>Error</dt><dd style={{ marginInlineStart: 0, whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, monospace' }}>{f.error || 'No error detail recorded'}</dd>
                      </dl>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></TableRegion>
        )}
      </div>
    </div>
  )
}
