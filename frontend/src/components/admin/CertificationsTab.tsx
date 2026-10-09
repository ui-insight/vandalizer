import { FullExportButton } from './shared/FullExportButton'
import { useAdminViewState } from './shared/AdminViewState'
import { CertificationRecoveryReview } from './CertificationRecoveryReview'
import { CertificationLearnerSummary } from './CertificationLearnerSummary'
import { CertificationAccessChange } from './CertificationAccessChange'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { AlertCircle, Award, Lock, RefreshCw, Unlock } from 'lucide-react'
import {
  getCertificationProgressList, setCertificationUnlock,
  type CertificationProgressItem,
  type CertificationAccessRequest,
} from '../../api/admin'
import { useToast } from '../../contexts/ToastContext'
import { downloadCSV, formatDate, formatNumber } from './shared/format'
import { ExportButton, SearchInput, UserAvatar } from './shared/primitives'

export function CertificationsTab() {
  const { toast } = useToast()
  const [search, setSearch] = useAdminViewState('CertificationsTab.search', '')
  const [query, setQuery] = useAdminViewState('CertificationsTab.query', '')
  const [offset, setOffset] = useAdminViewState('CertificationsTab.offset', 0)
  const pageSize = 100
  const [reviewing, setReviewing] = useState<CertificationProgressItem | null>(null)
  const [inspecting, setInspecting] = useState<CertificationProgressItem | null>(null)
  const [accessing, setAccessing] = useState<CertificationProgressItem | null>(null)
  const [busyUser, setBusyUser] = useState<string | null>(null)

  const recoveryTrigger = useRef<HTMLButtonElement | null>(null)
  const statusTrigger = useRef<HTMLButtonElement | null>(null)
  const accessTrigger = useRef<HTMLButtonElement | null>(null)
  const accessTarget = useRef<string | null>(null)
  const returnAccessFocus = useRef(false)
  const busyRef = useRef(false)
  const request = useCallback(() => getCertificationProgressList(pageSize, offset, query), [offset, query])
  const { data, setData, loading, error, load: refresh } = useAdminQuery(request)
  const items = useMemo(() => data?.items ?? [], [data])
  const capped = data?.capped ?? false
  useEffect(() => {
    if (returnAccessFocus.current && !accessing && !busyUser) {
      returnAccessFocus.current = false
      accessTrigger.current?.focus()
    }
  }, [accessing, busyUser])

  const filtered = items

  const toggleUnlock = async (item: CertificationProgressItem, request: CertificationAccessRequest) => {
    if (busyRef.current || item.can_unlock === false) return
    busyRef.current = true
    setBusyUser(item.user_id)
    try {
      const saved = await setCertificationUnlock(item.user_id, request, item.enrollment_id ?? undefined)
      setData(prev => prev ? { ...prev, items: prev.items.map(p =>
        p.user_id === item.user_id && p.progress_id === item.progress_id && p.enrollment_id === item.enrollment_id ? { ...p, unlocked: saved.unlocked } : p
      ) } : prev)
      setAccessing(null)
      returnAccessFocus.current = true
      toast('Access change recorded. Assessed credit is unchanged.', 'success')
    } finally {
      busyRef.current = false
      setBusyUser(null)
    }
  }

  const handleExport = () => {
    downloadCSV('certifications.csv',
      ['User', 'Email', 'Course', 'Version', 'Enrollment', 'Selected', 'State', 'Reconciliation', 'Level', 'Total XP', 'Modules Completed', 'Modules Total', 'Certified', 'Certified At', 'Last Activity', 'Unlocked', 'Study Order', 'Progression Policy'],
      filtered.map(p => [
        p.name || p.user_id, p.email,
        p.course_title ?? null, p.course_version ?? null, p.enrollment_id ?? null, p.is_active == null ? '' : p.is_active ? 'yes' : 'no', p.enrollment_state ?? null, p.reconciliation_error ?? null,
        p.level, p.total_xp,
        p.modules_completed, p.modules_total,
        p.certified ? 'yes' : 'no',
        p.certified_at,
        p.last_activity_date,
        p.learning_order === 'any_order' ? 'not applicable' : p.unlocked ? 'yes' : 'no',
        p.learning_order ?? null, p.progression_policy_id ?? null,
      ]),
      { Scope: 'Current page', Offset: String(offset), Search: query, Timezone: 'UTC' }
    )
  }

  if (loading && !data && !query && offset === 0) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading certification progress...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Certifications</h2>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
          Certification enrollments and preserved history. Only the selected course can be changed.
        </p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <form onSubmit={event => { event.preventDefault(); setOffset(0); setQuery(search.trim()); }} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search users or courses..." />
          <button type="submit" className="admin-open-record" disabled={loading}>Search all records</button>
        </form>
        <div style={{ flex: 1 }} />
        <button
          onClick={refresh}
          disabled={!!busyUser}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
        <ExportButton onClick={handleExport} disabled={loading || !!error || !data} />
        <FullExportButton scope={query} filename="certifications-all-matching.csv" disabled={loading || !!error}
          headers={['User', 'Email', 'Course', 'Version', 'Enrollment', 'Selected', 'State', 'Reconciliation', 'Level', 'Total XP', 'Modules Completed', 'Modules Total', 'Certified', 'Certified At', 'Last Activity', 'Unlocked', 'Study Order', 'Progression Policy']} fetchPage={offset => getCertificationProgressList(pageSize, offset, query)}
          getKey={item => item.progress_id || `${item.user_id}:${item.enrollment_id || ''}`}
          row={p => [
        p.name || p.user_id, p.email,
        p.course_title ?? null, p.course_version ?? null, p.enrollment_id ?? null, p.is_active == null ? '' : p.is_active ? 'yes' : 'no', p.enrollment_state ?? null, p.reconciliation_error ?? null,
        p.level, p.total_xp,
        p.modules_completed, p.modules_total,
        p.certified ? 'yes' : 'no',
        p.certified_at,
        p.last_activity_date,
        p.learning_order === 'any_order' ? 'not applicable' : p.unlocked ? 'yes' : 'no',
        p.learning_order ?? null, p.progression_policy_id ?? null,]} metadata={{ Search: query, Timezone: 'UTC' }} />
      </div>

      {reviewing && <CertificationRecoveryReview key={reviewing.enrollment_id} item={reviewing} onClose={() => { setReviewing(null); requestAnimationFrame(() => recoveryTrigger.current?.focus()) }} />}
      {inspecting && <CertificationLearnerSummary key={`${inspecting.user_id}:${inspecting.enrollment_id ?? inspecting.progress_id}`} item={inspecting} onClose={() => { setInspecting(null); requestAnimationFrame(() => statusTrigger.current?.focus()) }} />}
      {accessing && <CertificationAccessChange key={`${accessing.user_id}:${accessing.enrollment_id ?? accessing.progress_id}`} item={accessing} onApply={request => toggleUnlock(accessing, request)} onClose={() => { setAccessing(null); requestAnimationFrame(() => accessTrigger.current?.focus()) }} />}

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          Certification Progress ({data?.total ?? 0} matching records)
        </div>
        <div className="admin-pagination" aria-label="Certification pages">
          <p role="status">{loading ? 'Loading records…' : `${filtered.length ? offset + 1 : 0}–${offset + filtered.length} of ${data?.total ?? 0} matching records. Export CSV contains this page; Export all matching records includes every match.`}</p>
          <button type="button" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>Previous page</button>
          <button type="button" disabled={loading || !capped} onClick={() => setOffset(value => value + pageSize)}>Next page</button>
        </div>
        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
            color: '#991b1b', fontSize: 13,
          }}>
            <span role="alert"><AlertCircle size={14} /> {error}</span>
          </div>
        )}
        {filtered.length === 0 ? (
          !error && <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>{query ? 'No records match this search.' : 'No users have started the certification yet.'}</div>
        ) : (
          <TableRegion label="Certification progress — scroll for more columns"><table style={{ width: '100%', minWidth: 1080, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>User</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Level</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>XP</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Modules</th>
                <th style={{ padding: '10px 16px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Certified</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Last Active</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Course controls</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => {
                const pct = p.modules_total > 0 ? (p.modules_completed / p.modules_total) * 100 : 0
                return (
                  <tr key={p.progress_id ?? p.enrollment_id ?? p.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '12px 16px', minWidth: 280 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <UserAvatar name={p.name || p.email} />
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 500 }}>{p.name || 'Unknown'}</div>
                          <div style={{ fontSize: 12, color: '#6b7280' }}>{p.email || p.user_id}</div>
                          {p.course_title && <div style={{ fontSize: 12, color: '#374151', marginTop: 6 }}>{p.course_title}</div>}
                          {p.course_version && <div style={{ fontSize: 12, color: '#4b5563' }}>{p.course_version} · {p.is_active ? 'Selected course' : 'Preserved history'} · {p.enrollment_state}</div>}
                          {p.reconciliation_error && <div role="status" style={{ fontSize: 12, color: '#991b1b', marginTop: 4 }}>{p.reconciliation_error}</div>}
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
                          {p.reconciliation_error ? 'Unavailable' : `${p.modules_completed}/${p.modules_total}`}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      {p.certified ? (
                        <span title={p.certified_at ? `Certified ${formatDate(p.certified_at)}` : 'Certified'} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#15803d', fontSize: 13, fontWeight: 600 }}>
                          <Award size={14} /> Yes
                        </span>
                      ) : (
                        <span style={{ color: '#59616b', fontSize: 13 }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', whiteSpace: 'nowrap', fontSize: 13, color: '#6b7280' }}>
                      {p.last_activity_date || formatDate(p.updated_at)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <button type="button" style={{ minHeight: 44 }} onClick={event => { statusTrigger.current = event.currentTarget; setInspecting(p) }} className="mb-2 block rounded border border-gray-400 bg-white px-3 py-2 text-sm text-gray-900" aria-label={`View learning status for ${p.name || p.email || p.user_id}${p.course_title ? ` — ${p.course_title}` : ''}`}>View learning status</button>
                      {p.learning_order === 'any_order' ? <div className="text-sm text-gray-700"><p className="font-medium text-gray-900">Any study order</p><p className="mt-1">All required outcomes still apply.</p></div> : <button
                        ref={node => { if (accessTarget.current === (p.progress_id ?? p.enrollment_id ?? p.user_id)) accessTrigger.current = node }}
                        onClick={event => { accessTarget.current = p.progress_id ?? p.enrollment_id ?? p.user_id; accessTrigger.current = event.currentTarget; setAccessing(p) }}
                        disabled={!!busyUser || p.can_unlock === false}
                        aria-label={`${p.unlocked ? 'Re-lock' : 'Unlock'} prerequisites for ${p.name || p.email || p.user_id}${p.course_title ? ` — ${p.course_title}` : ''}`}
                        title={p.can_unlock === false ? (p.unlock_unavailable_reason || p.reconciliation_error || 'Only the selected enrollment can be changed') : p.unlocked
                          ? 'Re-lock prerequisites for this user'
                          : 'Unlock all units so this user can select any module without prerequisites'}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          padding: '5px 10px', border: '1px solid',
                          minHeight: 44,
                          borderColor: p.unlocked ? '#16a34a' : '#d1d5db',
                          borderRadius: 6, fontSize: 12, fontWeight: 500,
                          background: p.unlocked ? '#dcfce7' : '#fff',
                          color: p.unlocked ? '#166534' : '#374151',
                          cursor: p.can_unlock === false ? 'not-allowed' : busyUser === p.user_id ? 'wait' : 'pointer',
                          opacity: p.can_unlock === false || busyUser === p.user_id ? 0.6 : 1,
                          whiteSpace: 'nowrap',
                          fontFamily: 'inherit',
                        }}
                      >
                        {p.unlocked ? <><Unlock size={12} /> Unlocked</> : <><Lock size={12} /> Unlock</>}
                      </button>}
                      {p.enrollment_id && !p.reconciliation_error && <button type="button" onClick={event => { recoveryTrigger.current = event.currentTarget; setReviewing(p) }} className="mt-2 block rounded border border-gray-400 bg-white px-3 py-2 text-sm text-gray-900" aria-label={`${p.is_active ? 'Review completion recovery' : 'View completion recovery history'} for ${p.name || p.email || p.user_id}`}>{p.is_active ? 'Review recovery' : 'Recovery history'}</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table></TableRegion>
        )}
      </div>

      <div style={{ fontSize: 12, color: '#6b7280', padding: '8px 4px' }}>
        Module access controls do not complete assessments or award XP. Courses that allow
        any study order need no prerequisite override.
      </div>
    </div>
  )
}
