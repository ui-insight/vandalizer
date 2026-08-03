import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, Award, Lock, RefreshCw, Unlock } from 'lucide-react'
import {
  getCertificationProgressList, setCertificationUnlock,
  type CertificationProgressItem,
} from '../../api/admin'
import { useToast } from '../../contexts/ToastContext'
import { downloadCSV, formatDate, formatNumber } from './shared/format'
import { ExportButton, SearchInput, UserAvatar } from './shared/primitives'

export function CertificationsTab() {
  const { toast } = useToast()
  const [items, setItems] = useState<CertificationProgressItem[]>([])
  const [capped, setCapped] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [busyUser, setBusyUser] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getCertificationProgressList()
      setItems(data.items)
      setCapped(data.capped)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load certification progress')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const filtered = useMemo(() => {
    if (!search.trim()) return items
    const q = search.toLowerCase()
    return items.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.email || '').toLowerCase().includes(q) ||
      (p.user_id || '').toLowerCase().includes(q)
    )
  }, [items, search])

  const toggleUnlock = async (item: CertificationProgressItem) => {
    setBusyUser(item.user_id)
    try {
      await setCertificationUnlock(item.user_id, !item.unlocked)
      setItems(prev => prev.map(p =>
        p.user_id === item.user_id ? { ...p, unlocked: !item.unlocked } : p
      ))
    } catch (e) {
      toast(`Failed to ${item.unlocked ? 're-lock' : 'unlock'} certification for ${item.name || item.user_id}: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      setBusyUser(null)
    }
  }

  const handleExport = () => {
    downloadCSV('certifications.csv',
      ['User', 'Email', 'Level', 'Total XP', 'Modules Completed', 'Modules Total', 'Certified', 'Certified At', 'Streak', 'Last Activity', 'Unlocked'],
      filtered.map(p => [
        p.name || p.user_id, p.email,
        p.level, p.total_xp,
        p.modules_completed, p.modules_total,
        p.certified ? 'yes' : 'no',
        p.certified_at,
        p.streak_days,
        p.last_activity_date,
        p.unlocked ? 'yes' : 'no',
      ])
    )
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading certification progress...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Certifications</h2>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
          Users who have started the Vandal Workflow Architect certification and where they are in the program.
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Search users..." />
        <div style={{ flex: 1 }} />
        <button
          onClick={refresh}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          Certification Progress ({filtered.length})
        </div>
        {capped && (
          <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertCircle size={14} /> Showing the top {items.length} users by progress — this list is truncated. Search and export cover only these loaded rows, not every user.
          </div>
        )}
        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
            color: '#991b1b', fontSize: 13,
          }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}
        {filtered.length === 0 ? (
          !error && <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No users have started the certification yet.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>User</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Level</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>XP</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Modules</th>
                <th style={{ padding: '10px 16px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Certified</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Last Active</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Debug Unlock</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => {
                const pct = p.modules_total > 0 ? (p.modules_completed / p.modules_total) * 100 : 0
                return (
                  <tr key={p.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <UserAvatar name={p.name || p.email} />
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 500 }}>{p.name || 'Unknown'}</div>
                          <div style={{ fontSize: 12, color: '#6b7280' }}>{p.email || p.user_id}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
                        fontSize: 11, fontWeight: 700, backgroundColor: '#eef2ff', color: '#4338ca',
                        textTransform: 'uppercase', letterSpacing: 0.5,
                      }}>
                        {p.level}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(p.total_xp)}</td>
                    <td style={{ padding: '12px 16px', minWidth: 200 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ flex: 1, height: 6, backgroundColor: '#f3f4f6', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', backgroundColor: 'var(--highlight-color, #eab308)', borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: 12, color: '#6b7280', fontFamily: 'ui-monospace, monospace', minWidth: 48, textAlign: 'right' }}>
                          {p.modules_completed}/{p.modules_total}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      {p.certified ? (
                        <span title={p.certified_at ? `Certified ${formatDate(p.certified_at)}` : 'Certified'} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: 13, fontWeight: 600 }}>
                          <Award size={14} /> Yes
                        </span>
                      ) : (
                        <span style={{ color: '#9ca3af', fontSize: 13 }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>
                      {p.last_activity_date || formatDate(p.updated_at)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <button
                        onClick={() => toggleUnlock(p)}
                        disabled={busyUser === p.user_id}
                        title={p.unlocked
                          ? 'Re-lock prerequisites for this user'
                          : 'Unlock all units so this user can select any module without prerequisites'}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          padding: '5px 10px', border: '1px solid',
                          borderColor: p.unlocked ? '#16a34a' : '#d1d5db',
                          borderRadius: 6, fontSize: 12, fontWeight: 500,
                          background: p.unlocked ? '#dcfce7' : '#fff',
                          color: p.unlocked ? '#166534' : '#374151',
                          cursor: busyUser === p.user_id ? 'wait' : 'pointer',
                          opacity: busyUser === p.user_id ? 0.6 : 1,
                          fontFamily: 'inherit',
                        }}
                      >
                        {p.unlocked ? <><Unlock size={12} /> Unlocked</> : <><Lock size={12} /> Unlock</>}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ fontSize: 12, color: '#6b7280', padding: '8px 4px' }}>
        <strong>Note:</strong> The unlock toggle is a debugging aid. It lets a user select any unit
        in the certification program without completing the prerequisites — it does not mark
        modules as completed or grant XP.
      </div>
    </div>
  )
}
