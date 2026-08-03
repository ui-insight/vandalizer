import React, { useEffect, useState, useCallback, useMemo } from 'react'
import {
  AlertCircle, ChevronRight, RefreshCw, MessageSquare, Download, ChevronDown,
  Mail, Send, Link, UserPlus, Award,
} from 'lucide-react'
import { useConfirm } from '../shared/useConfirm'
import { useToast } from '../../contexts/ToastContext'
import {
  getDemoStats, getDemoApplications, releaseDemoUser, activateDemoUser, restartDemoTrial,
  promoteDemoUser,
  getPostExperienceResponses, sendTestEmail, adminResendCredentials, adminGetMagicLink,
  adminAddDemoUser,
} from '../../api/demo'
import { getAdminPromptOverview, adminUpdatePrompt, type PromptOverview } from '../../api/feedbackPrompt'
import * as supportApi from '../../api/support'
import type { SupportTicket, SupportTicketSummary } from '../../types/support'
import type { DemoAdminStats, DemoApplication as DemoApp, PostExperienceResponseAdmin } from '../../types/demo'
import { POST_SURVEY_FIELDS } from '../survey/postSurveyFields'
import { PRE_SURVEY_FIELDS } from '../survey/preSurveyFields'
import { SurveyFieldRenderer } from '../survey/SurveyFieldRenderer'
import { downloadCSV, formatDate } from './shared/format'
import { SearchInput } from './shared/primitives'

function DemoResponseDetail({ responses }: { responses: Record<string, unknown> }) {
  if (!responses || Object.keys(responses).length === 0) {
    return <div style={{ padding: '16px 0', color: '#9ca3af', fontSize: 13 }}>No onboarding responses recorded.</div>
  }

  // Group fields by section using the PRE_SURVEY_FIELDS definitions
  const sections: { name: string; items: { label: string; value: string }[] }[] = []
  let currentSection = ''
  let currentItems: { label: string; value: string }[] = []

  for (const field of PRE_SURVEY_FIELDS) {
    if (field.type === 'info') continue
    if (field.section && field.section !== currentSection) {
      if (currentItems.length > 0) sections.push({ name: currentSection, items: currentItems })
      currentSection = field.section
      currentItems = []
    }

    // Handle likert_group: each statement is a sub-key
    if (field.type === 'likert_group' && field.statements) {
      for (const stmt of field.statements) {
        const val = responses[stmt.key]
        if (val !== undefined && val !== null && val !== '') {
          currentItems.push({ label: stmt.label, value: String(val) })
        }
      }
      continue
    }

    const val = responses[field.key]
    if (val === undefined || val === null || val === '') continue
    const display = Array.isArray(val) ? val.join(', ') : String(val)
    currentItems.push({ label: field.label, value: display })
  }
  if (currentItems.length > 0) sections.push({ name: currentSection, items: currentItems })

  // Also show any keys not in PRE_SURVEY_FIELDS (future-proofing)
  const knownKeys = new Set(PRE_SURVEY_FIELDS.flatMap(f =>
    f.type === 'likert_group' && f.statements ? f.statements.map(s => s.key) : [f.key]
  ))
  const extraItems: { label: string; value: string }[] = []
  for (const [key, val] of Object.entries(responses)) {
    if (knownKeys.has(key) || val === undefined || val === null || val === '') continue
    const display = Array.isArray(val) ? val.join(', ') : String(val)
    extraItems.push({ label: key, value: display })
  }
  if (extraItems.length > 0) sections.push({ name: 'Other', items: extraItems })

  const likertLabels: Record<string, string> = {
    '1': 'Strongly Disagree',
    '2': 'Disagree',
    '3': 'Neutral',
    '4': 'Agree',
    '5': 'Strongly Agree',
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: '#111827' }}>Onboarding Responses</div>
      {sections.map((section) => (
        <div key={section.name} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            {section.name}
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            {section.items.map((item) => (
              <div key={item.label} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13, padding: '6px 0', borderBottom: '1px solid #f3f4f6' }}>
                <span style={{ color: '#374151', fontWeight: 500 }}>{item.label}</span>
                <span style={{ color: '#111827' }}>
                  {likertLabels[item.value] || (item.value.match(/^\d+$/) && item.label.toLowerCase().includes('minute') ? `${item.value} min` : item.value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function DemoTab() {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [subTab, setSubTab] = useState<'applications' | 'surveys'>('applications')
  const [stats, setStats] = useState<DemoAdminStats | null>(null)
  const [apps, setApps] = useState<DemoApp[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [s, a] = await Promise.all([
        getDemoStats(),
        getDemoApplications(statusFilter || undefined),
      ])
      setStats(s)
      setApps(a)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Failed to load demo applications')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadData() }, [loadData])

  // Client-side text search over the (status-filtered) applications.
  const filteredApps = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return apps
    return apps.filter(app =>
      app.name.toLowerCase().includes(q)
      || (app.title ?? '').toLowerCase().includes(q)
      || app.email.toLowerCase().includes(q)
      || app.organization.toLowerCase().includes(q),
    )
  }, [apps, search])

  const [actionLoading, setActionLoading] = useState<string | null>(null)

  async function handleExport() {
    setActionLoading('export')
    try {
      // Fetch all applications (unfiltered) and post-survey responses
      const [allApps, postResponses] = await Promise.all([
        getDemoApplications(),
        getPostExperienceResponses(),
      ])

      // Index post-survey responses by email for matching
      const postByEmail = new Map<string, Record<string, unknown>>()
      for (const pr of postResponses) {
        postByEmail.set(pr.email, pr.responses)
      }

      // Build pre-survey column definitions (key + label)
      const preCols: { key: string; label: string }[] = []
      for (const f of PRE_SURVEY_FIELDS) {
        if (f.type === 'info') continue
        if (f.type === 'likert_group' && f.statements) {
          for (const s of f.statements) preCols.push({ key: s.key, label: `Pre: ${s.label}` })
        } else {
          preCols.push({ key: f.key, label: `Pre: ${f.label}` })
        }
      }

      // Build post-survey column definitions
      const postCols: { key: string; label: string }[] = []
      for (const f of POST_SURVEY_FIELDS) {
        if (f.type === 'info') continue
        if (f.type === 'likert_group' && f.statements) {
          for (const s of f.statements) postCols.push({ key: s.key, label: `Post: ${s.label}` })
        } else {
          postCols.push({ key: f.key, label: `Post: ${f.label}` })
        }
      }

      const headers = [
        'Name', 'Title', 'Email', 'Organization', 'Status',
        'Applied', 'Activated', 'Credentials Sent', 'First Login',
        'Expires', 'Post-Survey Completed',
        ...preCols.map(c => c.label),
        ...postCols.map(c => c.label),
      ]

      const rows = allApps.map(app => {
        const pre = app.questionnaire_responses || {}
        const post = postByEmail.get(app.email) || {}
        const fmt = (v: unknown) => {
          if (v === null || v === undefined || v === '') return null
          return Array.isArray(v) ? v.join('; ') : String(v)
        }
        return [
          app.name,
          app.title || null,
          app.email,
          app.organization,
          app.status,
          app.created_at ? formatDate(app.created_at) : null,
          app.activated_at ? formatDate(app.activated_at) : null,
          app.credentials_sent_at ? formatDate(app.credentials_sent_at) : null,
          app.last_login_at ? formatDate(app.last_login_at) : 'Never',
          app.expires_at ? formatDate(app.expires_at) : null,
          app.post_questionnaire_completed ? 'Yes' : 'No',
          ...preCols.map(c => fmt(pre[c.key])),
          ...postCols.map(c => fmt(post[c.key])),
        ] as (string | number | null)[]
      })

      downloadCSV('demo_export.csv', headers, rows)
    } catch {
      toast('Failed to export demo data', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleActivate(uuid: string) {
    const ok = await confirm({
      title: 'Activate this application?',
      message: 'Activate this pending application now? This creates their account and sends login credentials immediately, skipping the waitlist queue.',
      confirmLabel: 'Activate',
    })
    if (!ok) return
    setActionLoading(`activate-${uuid}`)
    try {
      await activateDemoUser(uuid)
      loadData()
    } catch {
      toast('Failed to activate application', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleRelease(uuid: string) {
    const ok = await confirm({
      title: 'Release this user?',
      message: 'Release this user so they can log in again? This is typically used for expired or completed trials that no longer need admin follow-up.',
      confirmLabel: 'Release',
    })
    if (!ok) return
    setActionLoading(`release-${uuid}`)
    try {
      await releaseDemoUser(uuid)
      loadData()
    } catch {
      toast('Failed to release application', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleRestartTrial(uuid: string) {
    const ok = await confirm({
      title: 'Restart trial?',
      message: 'Restart this user\'s trial? They will get a fresh 14-day trial period starting now.',
      confirmLabel: 'Restart trial',
    })
    if (!ok) return
    setActionLoading(`restart-${uuid}`)
    try {
      await restartDemoTrial(uuid)
      loadData()
    } catch {
      toast('Failed to restart trial', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handlePromote(uuid: string, email: string) {
    const ok = await confirm({
      title: 'Promote to full user?',
      message: (
        <>
          Promote <strong>{email}</strong> to a permanent full user? Their trial expiry
          will be cleared and they'll keep their account, data, and team membership.
          This cannot be reversed from this screen.
        </>
      ),
      confirmLabel: 'Promote',
    })
    if (!ok) return
    setActionLoading(`promote-${uuid}`)
    try {
      await promoteDemoUser(uuid)
      loadData()
    } catch {
      toast('Failed to promote user', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleTestEmail(email: string) {
    setActionLoading(`test-${email}`)
    try {
      await sendTestEmail(email)
      toast(`Test email sent to ${email}`, 'success')
    } catch {
      toast('Failed to send test email. Check SMTP configuration.', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleResendCredentials(uuid: string, email: string) {
    const ok = await confirm({
      title: 'Resend credentials?',
      message: (
        <>
          Resend credentials to <strong>{email}</strong>? This will reset their password.
        </>
      ),
      confirmLabel: 'Resend',
      destructive: true,
    })
    if (!ok) return
    setActionLoading(`resend-${uuid}`)
    try {
      await adminResendCredentials(uuid)
      toast(`Credentials resent to ${email}`, 'success')
    } catch {
      toast('Failed to resend credentials', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleCopyMagicLink(uuid: string) {
    setActionLoading(`magic-${uuid}`)
    try {
      const result = await adminGetMagicLink(uuid)
      await navigator.clipboard.writeText(result.url)
      toast('Magic link copied to clipboard! It expires in 24 hours and can only be used once.', 'success')
    } catch {
      toast('Failed to generate magic link', 'error')
    } finally {
      setActionLoading(null)
    }
  }

  // --- Add user form ---
  const [showAddUser, setShowAddUser] = useState(false)
  const [addUserForm, setAddUserForm] = useState({ first_name: '', last_name: '', email: '' })
  const [addUserError, setAddUserError] = useState<string | null>(null)

  async function handleAddUser(e: React.FormEvent) {
    e.preventDefault()
    setAddUserError(null)
    setActionLoading('add-user')
    try {
      await adminAddDemoUser(addUserForm)
      setAddUserForm({ first_name: '', last_name: '', email: '' })
      setShowAddUser(false)
      loadData()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add user'
      setAddUserError(msg)
    } finally {
      setActionLoading(null)
    }
  }

  const statusColors: Record<string, { bg: string; text: string }> = {
    pending: { bg: '#fef3c7', text: '#92400e' },
    active: { bg: '#dcfce7', text: '#166534' },
    expired: { bg: '#fee2e2', text: '#991b1b' },
    completed: { bg: '#dbeafe', text: '#1e40af' },
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Demo Program</h2>
        {subTab === 'applications' && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setShowAddUser(!showAddUser)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', border: '1px solid #16a34a', borderRadius: 8,
                background: showAddUser ? '#f0fdf4' : '#fff', color: '#16a34a',
                cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', fontWeight: 600,
              }}
            >
              <UserPlus size={14} /> Add User
            </button>
            <button
              onClick={handleExport}
              disabled={actionLoading === 'export'}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
                background: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
                opacity: actionLoading === 'export' ? 0.5 : 1,
              }}
            >
              <Download size={14} /> {actionLoading === 'export' ? 'Exporting...' : 'Export CSV'}
            </button>
            <button
              onClick={loadData}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
                background: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
              }}
            >
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        )}
      </div>

      {/* Sub-tab bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 4,
        background: '#f9fafb', borderRadius: 10, padding: 4,
        width: 'fit-content', marginBottom: 20,
      }}>
        <button
          onClick={() => setSubTab('applications')}
          style={{
            padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 500,
            cursor: 'pointer', border: 'none', fontFamily: 'inherit',
            background: subTab === 'applications' ? 'var(--highlight-color, #eab308)' : 'transparent',
            color: subTab === 'applications' ? '#000' : '#6b7280',
          }}
        >
          Applications
        </button>
        <button
          onClick={() => setSubTab('surveys')}
          style={{
            padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 500,
            cursor: 'pointer', border: 'none', fontFamily: 'inherit',
            background: subTab === 'surveys' ? 'var(--highlight-color, #eab308)' : 'transparent',
            color: subTab === 'surveys' ? '#000' : '#6b7280',
          }}
        >
          Survey Responses
        </button>
      </div>

      {subTab === 'surveys' && <SurveyResponsesSection />}

      {subTab === 'applications' && (
      <>
      {/* Add user form */}
      {showAddUser && (
        <form onSubmit={handleAddUser} style={{
          marginBottom: 24, padding: 20, borderRadius: 12,
          border: '1px solid #bbf7d0', background: '#f0fdf4',
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>Add User to Trial</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 12, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>First Name</label>
              <input
                required
                value={addUserForm.first_name}
                onChange={(e) => setAddUserForm({ ...addUserForm, first_name: e.target.value })}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db',
                  fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Last Name</label>
              <input
                required
                value={addUserForm.last_name}
                onChange={(e) => setAddUserForm({ ...addUserForm, last_name: e.target.value })}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db',
                  fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#374151', marginBottom: 4 }}>Email</label>
              <input
                required
                type="email"
                value={addUserForm.email}
                onChange={(e) => setAddUserForm({ ...addUserForm, email: e.target.value })}
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db',
                  fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box',
                }}
              />
            </div>
            <button
              type="submit"
              disabled={actionLoading === 'add-user'}
              style={{
                padding: '8px 20px', borderRadius: 8, border: 'none',
                background: '#16a34a', color: '#fff', fontSize: 14, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
                opacity: actionLoading === 'add-user' ? 0.5 : 1,
              }}
            >
              {actionLoading === 'add-user' ? 'Adding...' : 'Add & Activate'}
            </button>
          </div>
          {addUserError && (
            <div style={{ marginTop: 8, color: '#dc2626', fontSize: 13 }}>{addUserError}</div>
          )}
        </form>
      )}

      {/* Stats cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 24 }}>
          {[
            { label: 'Total', value: stats.total_applications, color: '#6b7280' },
            { label: 'Active', value: stats.active_count, color: '#16a34a' },
            { label: 'Waitlist', value: stats.waitlist_count, color: '#d97706' },
            { label: 'Expired', value: stats.expired_count, color: '#dc2626' },
            { label: 'Completed', value: stats.completed_count, color: '#2563eb' },
          ].map((card) => (
            <div key={card.label} style={{
              padding: 20, borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff',
            }}>
              <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>{card.label}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: card.color }}>{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Organization breakdown */}
      {stats && stats.by_organization.length > 0 && (
        <div style={{ marginBottom: 24, padding: 20, borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff' }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>By Organization</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {stats.by_organization.map((org) => (
              <span key={org.organization} style={{
                padding: '4px 12px', borderRadius: 20, background: '#f3f4f6',
                fontSize: 13, color: '#374151',
              }}>
                {org.organization}: {org.count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        {['', 'pending', 'active', 'expired', 'completed'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '6px 16px', borderRadius: 20, border: '1px solid #e5e7eb',
              background: statusFilter === s ? '#111827' : '#fff',
              color: statusFilter === s ? '#fff' : '#374151',
              fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500,
            }}
          >
            {s || 'All'}
          </button>
        ))}
        <div style={{ marginLeft: 'auto' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, email, organization..." />
        </div>
      </div>

      {/* Applications table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>Loading...</div>
      ) : loadError && apps.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
          <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
          <div style={{ fontSize: 14, color: '#374151' }}>{loadError}</div>
        </div>
      ) : (
        <div style={{ borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', background: '#fff' }}>
          {loadError && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
              color: '#991b1b', fontSize: 13,
            }}>
              <AlertCircle size={14} /> {loadError}
            </div>
          )}
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Name</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Email</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Organization</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Status</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Applied</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Credentials Sent</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>First Login</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Expires</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredApps.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                    {search.trim() ? 'No applications match your search.' : 'No applications found.'}
                  </td>
                </tr>
              )}
              {filteredApps.map((app) => {
                const sc = statusColors[app.status] || { bg: '#f3f4f6', text: '#374151' }
                const isExpanded = expandedUuid === app.uuid
                return (
                  <React.Fragment key={app.uuid}>
                    <tr
                      onClick={() => setExpandedUuid(isExpanded ? null : app.uuid)}
                      style={{ borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6', cursor: 'pointer' }}
                    >
                      <td style={{ padding: '12px 16px', fontWeight: 500 }}>
                        <span style={{ marginRight: 6, color: '#9ca3af', fontSize: 11 }}>{isExpanded ? '▼' : '▶'}</span>
                        {app.name}
                        {app.title && <span style={{ color: '#9ca3af', fontWeight: 400, marginLeft: 6, fontSize: 12 }}>{app.title}</span>}
                      </td>
                      <td style={{ padding: '12px 16px', color: '#6b7280' }}>{app.email}</td>
                      <td style={{ padding: '12px 16px', color: '#6b7280' }}>{app.organization}</td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                          background: sc.bg, color: sc.text, fontSize: 12, fontWeight: 600,
                        }}>
                          {app.status}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                        {formatDate(app.created_at)}
                      </td>
                      <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                        {app.credentials_sent_at ? formatDate(app.credentials_sent_at) : '-'}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: 13 }}>
                        {app.last_login_at ? (
                          <span style={{ color: '#6b7280' }}>{formatDate(app.last_login_at)}</span>
                        ) : (
                          <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>Never</span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                        {app.expires_at ? formatDate(app.expires_at) : '-'}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }} onClick={(e) => e.stopPropagation()}>
                          {app.status === 'pending' && (
                            <button
                              onClick={() => handleActivate(app.uuid)}
                              disabled={actionLoading === `activate-${app.uuid}`}
                              style={{
                                padding: '4px 12px', borderRadius: 6, border: '1px solid #16a34a',
                                background: '#f0fdf4', color: '#16a34a', fontSize: 12, fontWeight: 600,
                                cursor: 'pointer', fontFamily: 'inherit',
                                opacity: actionLoading === `activate-${app.uuid}` ? 0.5 : 1,
                              }}
                            >
                              {actionLoading === `activate-${app.uuid}` ? 'Activating...' : 'Activate'}
                            </button>
                          )}
                          {(app.status === 'expired' || app.status === 'completed') && !app.admin_released && (
                            <button
                              onClick={() => handleRelease(app.uuid)}
                              disabled={actionLoading === `release-${app.uuid}`}
                              style={{
                                padding: '4px 12px', borderRadius: 6, border: '1px solid #2563eb',
                                background: '#eff6ff', color: '#2563eb', fontSize: 12, fontWeight: 600,
                                cursor: 'pointer', fontFamily: 'inherit',
                                opacity: actionLoading === `release-${app.uuid}` ? 0.5 : 1,
                              }}
                            >
                              {actionLoading === `release-${app.uuid}` ? 'Releasing...' : 'Release'}
                            </button>
                          )}
                          {(app.status === 'active' || app.status === 'expired' || app.status === 'completed') && (
                            <button
                              onClick={() => handleRestartTrial(app.uuid)}
                              disabled={actionLoading === `restart-${app.uuid}`}
                              title="Reset trial to 14 days and re-activate"
                              style={{
                                padding: '4px 12px', borderRadius: 6, border: '1px solid #d97706',
                                background: '#fffbeb', color: '#92400e', fontSize: 12, fontWeight: 600,
                                cursor: 'pointer', fontFamily: 'inherit',
                                opacity: actionLoading === `restart-${app.uuid}` ? 0.5 : 1,
                              }}
                            >
                              Restart Trial
                            </button>
                          )}
                          {(app.status === 'active' || app.status === 'expired' || app.status === 'completed') && app.user_is_demo && (
                            <button
                              onClick={() => handlePromote(app.uuid, app.email)}
                              disabled={actionLoading === `promote-${app.uuid}`}
                              title="Promote to permanent full user (clears trial expiry)"
                              style={{
                                display: 'flex', alignItems: 'center', gap: 4,
                                padding: '4px 12px', borderRadius: 6, border: '1px solid #16a34a',
                                background: '#f0fdf4', color: '#166534', fontSize: 12, fontWeight: 600,
                                cursor: 'pointer', fontFamily: 'inherit',
                                opacity: actionLoading === `promote-${app.uuid}` ? 0.5 : 1,
                              }}
                            >
                              <Award size={12} /> Promote
                            </button>
                          )}
                          {(app.status === 'active' || app.status === 'expired' || app.status === 'completed') && !app.user_is_demo && (
                            <span style={{ fontSize: 12, color: '#166534', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                              <Award size={12} /> Full user
                            </span>
                          )}
                          <button
                            onClick={() => handleTestEmail(app.email)}
                            disabled={actionLoading === `test-${app.email}`}
                            title={`Send test email to ${app.email}`}
                            style={{
                              display: 'flex', alignItems: 'center', gap: 4,
                              padding: '4px 12px', borderRadius: 6, border: '1px solid #6b7280',
                              background: '#f9fafb', color: '#374151', fontSize: 12, fontWeight: 600,
                              cursor: 'pointer', fontFamily: 'inherit',
                              opacity: actionLoading === `test-${app.email}` ? 0.5 : 1,
                            }}
                          >
                            <Mail size={12} /> Test Email
                          </button>
                          {app.status === 'active' && (
                            <>
                              <button
                                onClick={() => handleResendCredentials(app.uuid, app.email)}
                                disabled={actionLoading === `resend-${app.uuid}`}
                                title={`Resend credentials to ${app.email}`}
                                style={{
                                  display: 'flex', alignItems: 'center', gap: 4,
                                  padding: '4px 12px', borderRadius: 6, border: '1px solid #d97706',
                                  background: '#fffbeb', color: '#92400e', fontSize: 12, fontWeight: 600,
                                  cursor: 'pointer', fontFamily: 'inherit',
                                  opacity: actionLoading === `resend-${app.uuid}` ? 0.5 : 1,
                                }}
                              >
                                <Send size={12} /> Resend Creds
                              </button>
                              <button
                                onClick={() => handleCopyMagicLink(app.uuid)}
                                disabled={actionLoading === `magic-${app.uuid}`}
                                title="Copy a one-time magic login link"
                                style={{
                                  display: 'flex', alignItems: 'center', gap: 4,
                                  padding: '4px 12px', borderRadius: 6, border: '1px solid #7c3aed',
                                  background: '#f5f3ff', color: '#5b21b6', fontSize: 12, fontWeight: 600,
                                  cursor: 'pointer', fontFamily: 'inherit',
                                  opacity: actionLoading === `magic-${app.uuid}` ? 0.5 : 1,
                                }}
                              >
                                <Link size={12} /> Copy Magic Link
                              </button>
                            </>
                          )}
                          {app.admin_released && (
                            <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 500 }}>Released</span>
                          )}
                          {app.post_questionnaire_completed && (
                            <span style={{ fontSize: 12, color: '#6b7280' }}>Feedback done</span>
                          )}
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td colSpan={9} style={{ padding: '0 16px 20px', background: '#fafafa' }}>
                          <DemoResponseDetail responses={app.questionnaire_responses} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
              {apps.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                    No applications found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Trial Check-ins */}
      <CheckInConversationsSection />
      <TrialCheckinsSection />
      </>
      )}
    </div>
  )
}

function CheckInConversationsSection() {
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'in_progress' | 'closed'>('all')
  const [activeUuid, setActiveUuid] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const status = statusFilter === 'all' ? undefined : statusFilter
      const res = await supportApi.listTickets(status, 200, 0, undefined, undefined, 'feedback_prompt')
      setTickets(res.tickets)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const statusColors: Record<string, string> = {
    open: '#f59e0b',
    in_progress: '#3b82f6',
    closed: '#9ca3af',
  }

  const fmtTime = (iso: string | null) => {
    if (!iso) return ''
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  }

  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Check-ins</h3>
          <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0 0' }}>
            Conversations from trial check-in prompts. These do not appear in the Support Center.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {(['all', 'open', 'in_progress', 'closed'] as const).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              style={{
                padding: '4px 12px', fontSize: 12, fontWeight: statusFilter === s ? 600 : 400,
                borderRadius: 9999, border: '1px solid #e5e7eb', cursor: 'pointer',
                background: statusFilter === s ? '#111827' : '#fff',
                color: statusFilter === s ? '#fff' : '#6b7280',
                fontFamily: 'inherit',
              }}
            >
              {s === 'in_progress' ? 'In Progress' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
          <button
            onClick={load}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', border: '1px solid #e5e7eb', borderRadius: 8,
              background: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
            }}
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af' }}>Loading...</div>
      ) : tickets.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af', border: '1px solid #e5e7eb', borderRadius: 12 }}>
          No check-in conversations yet.
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid #e5e7eb' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>Subject</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>User</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Status</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Messages</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t) => {
                const isExpanded = activeUuid === t.uuid
                const subject = t.subject.replace(/^\[Check-in\]\s*/, '')
                return (
                  <React.Fragment key={t.uuid}>
                    <tr
                      onClick={() => setActiveUuid(isExpanded ? null : t.uuid)}
                      style={{ borderBottom: isExpanded ? 'none' : '1px solid #f3f4f6', cursor: 'pointer' }}
                    >
                      <td style={{ padding: '10px 16px', fontWeight: 500 }}>
                        <span style={{ marginRight: 6, color: '#9ca3af', fontSize: 11 }}>{isExpanded ? '▼' : '▶'}</span>
                        {subject}
                      </td>
                      <td style={{ padding: '10px 16px', color: '#6b7280' }}>{t.user_name || t.user_id}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                        <span style={{
                          fontSize: 11, padding: '2px 8px', borderRadius: 9999,
                          background: `${statusColors[t.status]}20`, color: statusColors[t.status], fontWeight: 600,
                        }}>
                          {t.status.replace('_', ' ')}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'center', color: '#6b7280' }}>{t.message_count}</td>
                      <td style={{ padding: '10px 16px', color: '#6b7280' }}>
                        {fmtTime(t.last_message_at || t.updated_at)}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td colSpan={5} style={{ padding: '0 16px 20px', background: '#fafafa' }}>
                          <CheckInConversation
                            ticketUuid={t.uuid}
                            onUpdate={load}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function CheckInConversation({ ticketUuid, onUpdate }: { ticketUuid: string; onUpdate: () => void }) {
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)

  const loadTicket = useCallback(async () => {
    try {
      const data = await supportApi.getTicket(ticketUuid)
      setTicket(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [ticketUuid])

  useEffect(() => {
    loadTicket()
    supportApi.markTicketRead(ticketUuid).catch(() => {})
  }, [loadTicket, ticketUuid])

  const handleSend = async () => {
    if (!reply.trim() || sending) return
    setSending(true)
    try {
      const updated = await supportApi.addMessage(ticketUuid, reply.trim())
      setTicket(updated)
      setReply('')
      onUpdate()
    } catch {
      // ignore
    } finally {
      setSending(false)
    }
  }

  const handleStatusChange = async (next: string) => {
    try {
      const updated = await supportApi.updateTicket(ticketUuid, { status: next })
      setTicket(updated)
      onUpdate()
    } catch {
      // ignore
    }
  }

  if (loading) {
    return <div style={{ padding: 16, color: '#9ca3af', fontSize: 13 }}>Loading conversation...</div>
  }

  if (!ticket) {
    return <div style={{ padding: 16, color: '#9ca3af', fontSize: 13 }}>Failed to load ticket.</div>
  }

  return (
    <div style={{ paddingTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          {ticket.user_email && <span>{ticket.user_email} · </span>}
          opened {ticket.created_at ? new Date(ticket.created_at).toLocaleString() : ''}
        </div>
        {ticket.status !== 'closed' ? (
          <select
            value={ticket.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            style={{ fontSize: 12, padding: '4px 8px', borderRadius: 8, border: '1px solid #d1d5db', fontFamily: 'inherit' }}
          >
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="closed">Closed</option>
          </select>
        ) : (
          <button
            onClick={() => handleStatusChange('open')}
            style={{
              fontSize: 12, padding: '4px 10px', borderRadius: 8,
              border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            Reopen
          </button>
        )}
      </div>

      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: 12, display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 360, overflowY: 'auto',
      }}>
        {ticket.messages.map((m) => {
          const isSupport = m.is_support_reply
          return (
            <div key={m.uuid} style={{ display: 'flex', flexDirection: 'column', alignItems: isSupport ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '85%', padding: '8px 12px', borderRadius: 10,
                background: isSupport ? '#2563eb' : '#f3f4f6',
                color: isSupport ? '#fff' : '#111827',
              }}>
                <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 2, color: isSupport ? 'rgba(255,255,255,0.85)' : '#6b7280' }}>
                  {m.user_name || m.user_id}
                  {isSupport && <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 500, opacity: 0.85 }}>Team</span>}
                </div>
                <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                <div style={{ fontSize: 10, marginTop: 2, color: isSupport ? 'rgba(255,255,255,0.75)' : '#9ca3af' }}>
                  {m.created_at ? new Date(m.created_at).toLocaleString() : ''}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {ticket.status !== 'closed' ? (
        <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder="Reply to this check-in..."
            style={{
              flex: 1, padding: '8px 12px', fontSize: 13,
              border: '1px solid #d1d5db', borderRadius: 8, outline: 'none', fontFamily: 'inherit',
            }}
          />
          <button
            onClick={handleSend}
            disabled={sending || !reply.trim()}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '8px 14px', borderRadius: 8, border: 'none',
              background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600,
              cursor: reply.trim() && !sending ? 'pointer' : 'not-allowed',
              opacity: sending ? 0.6 : 1, fontFamily: 'inherit',
            }}
          >
            <Send size={14} /> {sending ? 'Sending...' : 'Reply'}
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 10, padding: '8px 12px', fontSize: 12, color: '#6b7280', textAlign: 'center' }}>
          This conversation is closed. Reopen to send a reply.
        </div>
      )}
    </div>
  )
}

function TrialCheckinsSection() {
  const { toast } = useToast()
  const [prompts, setPrompts] = useState<PromptOverview[]>([])
  const [loading, setLoading] = useState(true)

  const loadPrompts = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAdminPromptOverview()
      setPrompts(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadPrompts() }, [loadPrompts])

  async function toggleEnabled(slug: string, enabled: boolean) {
    try {
      await adminUpdatePrompt(slug, { enabled })
      loadPrompts()
    } catch (e) {
      toast(`Failed to ${enabled ? 'enable' : 'disable'} check-in prompt: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    }
  }

  const stageColors: Record<string, { bg: string; text: string }> = {
    early: { bg: '#dbeafe', text: '#1e40af' },
    mid: { bg: '#fef3c7', text: '#92400e' },
    late: { bg: '#fee2e2', text: '#991b1b' },
  }

  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Trial Check-ins</h3>
        <button
          onClick={loadPrompts}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', border: '1px solid #e5e7eb', borderRadius: 8,
            background: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
          }}
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>
      <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
        Proactive check-in prompts delivered through the support panel during the trial.
        Responses appear as support tickets.
      </p>

      {loading ? (
        <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af' }}>Loading...</div>
      ) : prompts.length === 0 ? (
        <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af' }}>
          No prompts configured. They will be seeded on next server restart.
        </div>
      ) : (
        <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid #e5e7eb' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>Stage</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600 }}>Subject</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, maxWidth: 300 }}>Question</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Shown</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Responded</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Dismissed</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Rate</th>
                <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map((p) => {
                const sc = stageColors[p.stage] || { bg: '#f3f4f6', text: '#374151' }
                return (
                  <tr key={p.slug} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 600,
                        background: sc.bg, color: sc.text,
                      }}>
                        {p.stage}
                      </span>
                    </td>
                    <td style={{ padding: '10px 16px', fontWeight: 500 }}>{p.subject}</td>
                    <td style={{ padding: '10px 16px', maxWidth: 300, color: '#6b7280' }}>
                      <span title={p.question_text}>
                        {p.question_text.length > 80 ? p.question_text.slice(0, 80) + '...' : p.question_text}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'center' }}>{p.stats.shown}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600, color: '#16a34a' }}>
                      {p.stats.responded}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'center', color: '#9ca3af' }}>{p.stats.dismissed}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                      {p.stats.shown > 0 ? `${Math.round(p.stats.response_rate * 100)}%` : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                      <button
                        onClick={() => toggleEnabled(p.slug, !p.enabled)}
                        style={{
                          width: 36, height: 20, borderRadius: 10, border: 'none',
                          background: p.enabled ? '#16a34a' : '#d1d5db',
                          cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
                        }}
                      >
                        <span style={{
                          position: 'absolute', top: 2, left: p.enabled ? 18 : 2,
                          width: 16, height: 16, borderRadius: '50%', background: '#fff',
                          transition: 'left 0.2s', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
                        }} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SurveyResponsesSection() {
  const [responses, setResponses] = useState<PostExperienceResponseAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [previewAnswers, setPreviewAnswers] = useState<Record<string, unknown>>({})
  const previewSections = useMemo(() => {
    const sections: { name: string; fields: typeof POST_SURVEY_FIELDS }[] = []
    let current: { name: string; fields: typeof POST_SURVEY_FIELDS } | null = null
    for (const f of POST_SURVEY_FIELDS) {
      const sec = f.section || ''
      if (!current || current.name !== sec) {
        current = { name: sec, fields: [] }
        sections.push(current)
      }
      current.fields.push(f)
    }
    return sections
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getPostExperienceResponses()
      setResponses(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  function renderValue(val: unknown): string {
    if (val === null || val === undefined) return '-'
    if (Array.isArray(val)) return val.join(', ')
    if (typeof val === 'object') {
      return Object.entries(val as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${v}`)
        .join('; ')
    }
    return String(val)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Survey Responses</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => { setShowPreview(!showPreview); setPreviewAnswers({}) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
              background: showPreview ? '#111827' : '#fff',
              color: showPreview ? '#fff' : '#374151',
              cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
            }}
          >
            <MessageSquare size={14} /> {showPreview ? 'Hide Preview' : 'Preview Post-Survey'}
          </button>
          <button
            onClick={loadData}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
              background: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
            }}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {showPreview && (
        <div style={{
          marginBottom: 24, padding: 24, borderRadius: 12,
          border: '1px solid #e5e7eb', background: '#0a0a0a',
          color: '#e5e7eb',
        }}>
          <div style={{ textAlign: 'center', marginBottom: 20 }}>
            <MessageSquare size={32} color="#f1b300" style={{ margin: '0 auto 8px' }} />
            <h3 style={{ fontSize: 18, fontWeight: 700, color: '#fff', margin: 0 }}>
              Post-Survey Preview
            </h3>
            <p style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>
              This is what participants see after their demo expires.
            </p>
          </div>
          {previewSections.map((sec) => (
            <div key={sec.name} style={{
              marginBottom: 16, border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 12, overflow: 'hidden',
            }}>
              <div style={{
                padding: '10px 16px', background: 'rgba(255,255,255,0.05)',
                fontSize: 12, fontWeight: 700, color: '#f1b300',
                textTransform: 'uppercase', letterSpacing: '0.05em',
              }}>
                {sec.name}
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
                {sec.fields.map((field) => (
                  <div key={field.key}>
                    <label style={{
                      display: 'block', fontSize: 13, fontWeight: 500,
                      color: '#d1d5db', marginBottom: 6,
                    }}>
                      {field.label}{field.required ? ' *' : ''}
                    </label>
                    <SurveyFieldRenderer
                      field={field}
                      value={previewAnswers[field.key]}
                      onChange={(k, v) => setPreviewAnswers(prev => ({ ...prev, [k]: v }))}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>Loading...</div>
      ) : responses.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
          No survey responses yet.
        </div>
      ) : (
        <div style={{ borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', background: '#fff' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Name</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Email</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Organization</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {responses.map((resp) => (
                <React.Fragment key={resp.uuid}>
                  <tr
                    onClick={() => setExpandedUuid(expandedUuid === resp.uuid ? null : resp.uuid)}
                    style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}
                  >
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {expandedUuid === resp.uuid ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        {resp.name}
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{resp.email}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{resp.organization}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                      {formatDate(resp.created_at)}
                    </td>
                  </tr>
                  {expandedUuid === resp.uuid && (
                    <tr>
                      <td colSpan={4} style={{ padding: '0 16px 16px 40px', background: '#fafbfc' }}>
                        {/* Pre-Survey (Questionnaire) */}
                        {Object.keys(resp.questionnaire_responses).length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <div style={{
                              fontSize: 13, fontWeight: 700, color: '#111827',
                              marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em',
                            }}>
                              Pre-Survey
                            </div>
                            <div style={{
                              display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 16px',
                              padding: 16, borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff',
                            }}>
                              {resp.title && (
                                <React.Fragment>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>title</div>
                                  <div style={{ fontSize: 13, color: '#6b7280' }}>{resp.title}</div>
                                </React.Fragment>
                              )}
                              {Object.entries(resp.questionnaire_responses).map(([key, val]) => (
                                <React.Fragment key={key}>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                                    {key.replace(/_/g, ' ')}
                                  </div>
                                  <div style={{ fontSize: 13, color: '#6b7280', wordBreak: 'break-word' }}>
                                    {renderValue(val)}
                                  </div>
                                </React.Fragment>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Post-Survey (Feedback) */}
                        <div style={{ marginTop: 12 }}>
                          <div style={{
                            fontSize: 13, fontWeight: 700, color: '#111827',
                            marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em',
                          }}>
                            Post-Survey
                          </div>
                          <div style={{
                            display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 16px',
                            padding: 16, borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff',
                          }}>
                            {Object.entries(resp.responses).map(([key, val]) => (
                              <React.Fragment key={key}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                                  {key.replace(/_/g, ' ')}
                                </div>
                                <div style={{ fontSize: 13, color: '#6b7280', wordBreak: 'break-word' }}>
                                  {renderValue(val)}
                                </div>
                              </React.Fragment>
                            ))}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

