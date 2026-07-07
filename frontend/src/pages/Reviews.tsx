import { useEffect, useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { CheckCircle2, Clock, XCircle, AlertTriangle, Inbox, Users } from 'lucide-react'
import { listMyReviews, listTeamReviews } from '../api/reviews'
import type { ReviewSummary, ReviewStatus } from '../api/reviews'
import { useAuth } from '../hooks/useAuth'
import { relativeTime } from '../utils/time'

type Tab = 'mine' | 'team'

const STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  escalated: 'Escalated',
}

function StatusPill({ status }: { status: ReviewStatus }) {
  const styles: Record<ReviewStatus, { bg: string; fg: string; Icon: typeof Clock }> = {
    pending: { bg: '#fef3c7', fg: '#92400e', Icon: Clock },
    approved: { bg: '#dcfce7', fg: '#166534', Icon: CheckCircle2 },
    rejected: { bg: '#fee2e2', fg: '#991b1b', Icon: XCircle },
    expired: { bg: '#e5e7eb', fg: '#374151', Icon: AlertTriangle },
    escalated: { bg: '#fed7aa', fg: '#9a3412', Icon: AlertTriangle },
  }
  const s = styles[status]
  const Icon = s.Icon
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', borderRadius: 999, fontSize: 11,
      fontWeight: 600, backgroundColor: s.bg, color: s.fg,
    }}>
      <Icon style={{ width: 12, height: 12 }} />
      {STATUS_LABEL[status]}
    </span>
  )
}

function dueLabel(review: ReviewSummary): string | null {
  if (!review.expires_at) return null
  const due = new Date(review.expires_at).getTime()
  const now = Date.now()
  if (due <= now) return 'Past due'
  const days = Math.ceil((due - now) / (24 * 3600 * 1000))
  if (days === 1) return 'Due tomorrow'
  return `Due in ${days} days`
}

export default function Reviews() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('mine')
  const [statusFilter, setStatusFilter] = useState<string>('pending')
  const [reviews, setReviews] = useState<ReviewSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const promise = tab === 'mine'
      ? listMyReviews(statusFilter === 'all' ? 'all' : statusFilter)
      : listTeamReviews(user?.current_team_uuid || undefined, statusFilter === 'all' ? 'all' : statusFilter)
    promise
      .then(d => { if (!cancelled) setReviews(d.reviews) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load reviews') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [tab, statusFilter, user?.current_team_uuid])

  const sorted = useMemo(() => {
    return [...reviews].sort((a, b) => {
      // Pending first, then most recent
      if (a.status === 'pending' && b.status !== 'pending') return -1
      if (a.status !== 'pending' && b.status === 'pending') return 1
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0
      return bTime - aTime
    })
  }, [reviews])

  return (
    <>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-highlight">Skip to main content</a>
    <main id="main-content" style={{ maxWidth: 920, margin: '0 auto', padding: '32px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#111827', margin: 0 }}>Reviews</h1>
        <Link to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined, project: undefined, workflow_share_token: undefined } as never} style={{ fontSize: 13, color: '#6b7280', textDecoration: 'none' }}>
          Back to workspace
        </Link>
      </div>

      <div style={{ display: 'flex', borderBottom: '1px solid #e5e7eb', marginBottom: 16 }}>
        <button
          onClick={() => setTab('mine')}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: tab === 'mine' ? 700 : 500,
            background: 'none', border: 'none', cursor: 'pointer',
            borderBottom: tab === 'mine' ? '2px solid #eab308' : '2px solid transparent',
            color: tab === 'mine' ? '#eab308' : '#6b7280',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}
        >
          <Inbox style={{ width: 14, height: 14 }} />
          My reviews
        </button>
        <button
          onClick={() => setTab('team')}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: tab === 'team' ? 700 : 500,
            background: 'none', border: 'none', cursor: 'pointer',
            borderBottom: tab === 'team' ? '2px solid #eab308' : '2px solid transparent',
            color: tab === 'team' ? '#eab308' : '#6b7280',
            display: 'inline-flex', alignItems: 'center', gap: 6,
          }}
        >
          <Users style={{ width: 14, height: 14 }} />
          Team queue
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <label style={{ fontSize: 12, color: '#6b7280' }}>Status</label>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          style={{
            padding: '4px 10px', fontSize: 13, border: '1px solid #d1d5db',
            borderRadius: 6, background: '#fff', color: '#374151',
          }}
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="expired">Expired</option>
          <option value="all">All</option>
        </select>
      </div>

      {loading && <div role="status" aria-live="polite" style={{ fontSize: 13, color: '#6b7280' }}>Loading...</div>}
      {error && <div role="status" aria-live="polite" style={{ fontSize: 13, color: '#dc2626' }}>{error}</div>}

      {!loading && sorted.length === 0 && (
        <div role="status" aria-live="polite" style={{ padding: 32, textAlign: 'center', fontSize: 13, color: '#6b7280', border: '1px dashed #e5e7eb', borderRadius: 8 }}>
          {tab === 'mine'
            ? 'Nothing waiting for you.'
            : 'No reviews open on this team.'}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sorted.map(r => {
          const due = dueLabel(r)
          return (
            <Link
              key={r.uuid}
              to={`/reviews/$uuid` as never}
              params={{ uuid: r.uuid } as never}
              style={{
                display: 'block', padding: 14, borderRadius: 8,
                border: '1px solid #e5e7eb', background: '#fff',
                textDecoration: 'none', color: 'inherit',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {r.workflow_name || 'Workflow'}
                  </div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                    Step "{r.step_name}"
                    {r.created_at ? ` · opened ${relativeTime(r.created_at)}` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  {due && (
                    <span style={{
                      fontSize: 11, fontWeight: 600,
                      color: due === 'Past due' ? '#991b1b' : '#92400e',
                    }}>
                      {due}
                    </span>
                  )}
                  <StatusPill status={r.status} />
                </div>
              </div>
            </Link>
          )
        })}
      </div>
    </main>
    </>
  )
}
