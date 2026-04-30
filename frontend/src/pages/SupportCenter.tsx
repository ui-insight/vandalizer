import { useEffect, useState, useCallback, useRef } from 'react'
import { Navigate, useNavigate, useSearch } from '@tanstack/react-router'
import {
  ArrowLeft, MessageSquare, Send, Plus, Paperclip, X, Loader2, Link2,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import * as supportApi from '../api/support'
import type {
  SupportTicket, SupportTicketSummary, SupportAttachment,
} from '../types/support'

type View = 'list' | 'new' | 'chat'
type StatusFilter = 'all' | 'open' | 'in_progress' | 'closed'

const MAX_BYTES = 10 * 1024 * 1024

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const STATUS_COLORS: Record<string, string> = {
  open: '#f59e0b',
  in_progress: '#3b82f6',
  closed: '#9ca3af',
}
const PRIORITY_COLORS: Record<string, string> = {
  low: '#9ca3af',
  normal: '#3b82f6',
  high: '#ef4444',
}

type Stats = { total: number; open: number; in_progress: number; closed: number }

export default function SupportCenter() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const search = useSearch({ from: '/support' }) as { ticket?: string }
  const { toast } = useToast()

  const [view, setView] = useState<View>('list')
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [loading, setLoading] = useState(true)
  const [activeTicketUuid, setActiveTicketUuid] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const statusParam = statusFilter === 'all' ? undefined : statusFilter
      const [s, t] = await Promise.all([
        supportApi.getTicketStats(),
        supportApi.listTickets(statusParam, 200),
      ])
      setStats(s)
      setTickets(t.tickets)
    } catch {
      toast('Failed to load tickets', 'error')
    } finally {
      setLoading(false)
    }
  }, [toast, statusFilter])

  useEffect(() => { load() }, [load])

  // Keep the URL in sync with the open ticket so agents can copy the address
  // bar (or the explicit Copy link button) and share it with each other.
  useEffect(() => {
    if (search.ticket && search.ticket !== activeTicketUuid) {
      setActiveTicketUuid(search.ticket)
      setView('chat')
    } else if (!search.ticket && view === 'chat') {
      setActiveTicketUuid(null)
      setView('list')
    }
  }, [search.ticket, activeTicketUuid, view])

  if (!user?.is_support_agent) {
    return <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined }} />
  }

  const openTicket = (uuid: string) => {
    setActiveTicketUuid(uuid)
    setView('chat')
    navigate({ to: '/support', search: { ticket: uuid } })
  }

  const backToList = () => {
    setActiveTicketUuid(null)
    setView('list')
    navigate({ to: '/support', search: { ticket: undefined } })
    load()
  }

  return (
    <PageLayout>
      {view === 'list' && (
        <ListView
          tickets={tickets}
          stats={stats}
          loading={loading}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          currentUserId={user.user_id}
          onNew={() => setView('new')}
          onSelect={openTicket}
        />
      )}
      {view === 'new' && (
        <NewTicketView
          onBack={() => setView('list')}
          onCreated={(t) => {
            openTicket(t.uuid)
            load()
          }}
        />
      )}
      {view === 'chat' && activeTicketUuid && (
        <ChatView
          key={activeTicketUuid}
          ticketUuid={activeTicketUuid}
          onBack={backToList}
        />
      )}
    </PageLayout>
  )
}

// ---------------------------------------------------------------------------
// List view — full queue with stats, status filter, and requester-aware rows
// ---------------------------------------------------------------------------

function ListView({
  tickets, stats, loading, statusFilter, onStatusFilterChange, currentUserId, onNew, onSelect,
}: {
  tickets: SupportTicketSummary[]
  stats: Stats | null
  loading: boolean
  statusFilter: StatusFilter
  onStatusFilterChange: (s: StatusFilter) => void
  currentUserId: string
  onNew: () => void
  onSelect: (uuid: string) => void
}) {
  const statCardStyle = (color: string): React.CSSProperties => ({
    flex: 1, padding: '16px 20px', background: '#fff', borderRadius: 'var(--ui-radius, 12px)',
    border: '1px solid #e5e7eb', borderLeft: `4px solid ${color}`,
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <MessageSquare size={20} color="#6b7280" />
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Support Center</h1>
            <p style={{ margin: '2px 0 0', fontSize: 13, color: '#6b7280' }}>
              Triage and respond to all support tickets.
            </p>
          </div>
        </div>
        <button
          onClick={onNew}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
            background: '#2563eb', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <Plus size={16} /> New Ticket
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={statCardStyle('#6b7280')}>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{stats.total}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>Total Tickets</div>
          </div>
          <div style={statCardStyle('#f59e0b')}>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#f59e0b' }}>{stats.open}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>Open</div>
          </div>
          <div style={statCardStyle('#3b82f6')}>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#3b82f6' }}>{stats.in_progress}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>In Progress</div>
          </div>
          <div style={statCardStyle('#22c55e')}>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#22c55e' }}>{stats.closed}</div>
            <div style={{ fontSize: 13, color: '#6b7280' }}>Closed</div>
          </div>
        </div>
      )}

      {/* Ticket list */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Tickets</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {(['all', 'open', 'in_progress', 'closed'] as StatusFilter[]).map(s => (
              <button
                key={s}
                onClick={() => onStatusFilterChange(s)}
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
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
            <Loader2 size={20} style={{ display: 'inline-block', animation: 'spin 1s linear infinite', verticalAlign: 'middle' }} />
            <span style={{ marginLeft: 8 }}>Loading...</span>
          </div>
        ) : tickets.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
            <MessageSquare size={28} color="#d1d5db" style={{ display: 'block', margin: '0 auto 8px' }} />
            <div style={{ fontSize: 14 }}>No tickets {statusFilter !== 'all' ? `with status "${statusFilter.replace('_', ' ')}"` : 'yet'}.</div>
          </div>
        ) : (
          <div>
            {tickets.map((t) => {
              const needsAttention =
                t.status !== 'closed'
                && t.last_message_user_id !== null
                && t.last_message_is_support_reply === false
                && !t.read_by?.includes(currentUserId)
              return (
                <button
                  key={t.uuid}
                  onClick={() => onSelect(t.uuid)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    width: '100%', padding: '12px 20px', borderBottom: '1px solid #f3f4f6',
                    background: needsAttention ? '#fffbeb' : '#fff',
                    border: 'none', borderTop: 'none', borderLeft: 'none', borderRight: 'none',
                    cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => { if (!needsAttention) (e.currentTarget as HTMLButtonElement).style.background = '#f9fafb' }}
                  onMouseLeave={(e) => { if (!needsAttention) (e.currentTarget as HTMLButtonElement).style.background = '#fff' }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {needsAttention && <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#3b82f6', flexShrink: 0 }} />}
                      <span style={{ fontSize: 14, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t.subject}
                      </span>
                      <span style={{
                        fontSize: 11, padding: '1px 6px', borderRadius: 9999,
                        background: `${STATUS_COLORS[t.status]}20`, color: STATUS_COLORS[t.status], fontWeight: 600,
                      }}>
                        {t.status.replace('_', ' ')}
                      </span>
                      <span style={{
                        fontSize: 11, padding: '1px 6px', borderRadius: 9999,
                        background: `${PRIORITY_COLORS[t.priority]}20`, color: PRIORITY_COLORS[t.priority], fontWeight: 600,
                      }}>
                        {t.priority}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.user_name || t.user_id} &middot; {t.message_count} message{t.message_count !== 1 ? 's' : ''}
                      {t.last_message_preview ? ` — ${t.last_message_preview}` : ''}
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: '#9ca3af', flexShrink: 0, marginLeft: 16 }}>
                    {timeAgo(t.updated_at || t.created_at)}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// New ticket form (agents file test tickets here for QA)
// ---------------------------------------------------------------------------

function NewTicketView({
  onBack, onCreated,
}: {
  onBack: () => void
  onCreated: (ticket: SupportTicket) => void
}) {
  const { toast } = useToast()
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [priority, setPriority] = useState('normal')
  const [files, setFiles] = useState<File[]>([])
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ''
    const accepted: File[] = []
    for (const f of picked) {
      if (f.size > MAX_BYTES) { toast(`${f.name} is over 10MB`, 'error'); continue }
      accepted.push(f)
    }
    if (accepted.length) setFiles((prev) => [...prev, ...accepted])
  }

  const handleSubmit = async () => {
    if (!subject.trim() || !message.trim()) return
    setSubmitting(true)
    try {
      const ticket = await supportApi.createTicket(subject.trim(), message.trim(), priority, files)
      toast('Ticket created', 'success')
      onCreated(ticket)
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to create ticket', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const labelStyle = { display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }
  const inputStyle = {
    width: '100%', padding: '8px 12px', fontSize: 14, fontFamily: 'inherit',
    border: '1px solid #d1d5db', borderRadius: 'var(--ui-radius, 12px)', outline: 'none',
    boxSizing: 'border-box' as const,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 720 }}>
      <button
        onClick={onBack}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px',
          border: '1px solid #d1d5db', borderRadius: 'var(--ui-radius, 12px)', background: '#fff',
          fontSize: 13, cursor: 'pointer', alignSelf: 'flex-start',
        }}
      >
        <ArrowLeft size={14} /> Back to tickets
      </button>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 24 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700 }}>File a Ticket</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: '#6b7280' }}>
          Drops into the same queue as customer tickets — useful for QA and dogfooding the support flow.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Subject</label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Brief summary of your issue"
              style={inputStyle}
              autoFocus
            />
          </div>
          <div>
            <label style={labelStyle}>Priority</label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              style={inputStyle}
            >
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Description</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={6}
              placeholder="What's going on? Include reproduction steps when possible."
              style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
            />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <label style={labelStyle}>Attachments</label>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 10px',
                  border: '1px solid #d1d5db', borderRadius: 'var(--ui-radius, 12px)', background: '#fff',
                  fontSize: 12, cursor: 'pointer',
                }}
              >
                <Paperclip size={12} /> Attach
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={onPickFiles}
                style={{ display: 'none' }}
              />
            </div>
            {files.length > 0 && (
              <ul style={{ margin: '8px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {files.map((f, i) => (
                  <li
                    key={`${f.name}-${i}`}
                    style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
                      padding: '6px 10px', background: '#f9fafb', border: '1px solid #e5e7eb',
                      borderRadius: 'var(--ui-radius, 12px)', fontSize: 12,
                    }}
                  >
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={f.name}>{f.name}</span>
                    <button
                      type="button"
                      onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 2 }}
                      title="Remove"
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div style={{ marginTop: 20, display: 'flex', gap: 8 }}>
          <button
            onClick={handleSubmit}
            disabled={!subject.trim() || !message.trim() || submitting}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
              background: '#2563eb', color: '#fff', fontSize: 14, fontWeight: 600,
              cursor: (!subject.trim() || !message.trim() || submitting) ? 'not-allowed' : 'pointer',
              opacity: (!subject.trim() || !message.trim() || submitting) ? 0.6 : 1,
            }}
          >
            {submitting && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />}
            Submit Ticket
          </button>
          <button
            onClick={onBack}
            style={{
              padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)',
              border: '1px solid #d1d5db', background: '#fff',
              fontSize: 14, fontWeight: 500, cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chat view — agent mode: status controls, agent/customer message styling
// ---------------------------------------------------------------------------

function ChatView({
  ticketUuid, onBack,
}: {
  ticketUuid: string
  onBack: () => void
}) {
  const { toast } = useToast()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [previewAttachment, setPreviewAttachment] = useState<SupportAttachment | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadTicket = useCallback(async () => {
    try {
      const data = await supportApi.getTicket(ticketUuid)
      setTicket(data)
    } catch {
      toast('Failed to load ticket', 'error')
    } finally {
      setLoading(false)
    }
  }, [ticketUuid, toast])

  useEffect(() => {
    loadTicket()
    supportApi.markTicketRead(ticketUuid).catch(() => {})
    const interval = setInterval(loadTicket, 15000)
    return () => clearInterval(interval)
  }, [loadTicket, ticketUuid])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [ticket?.messages.length])

  const handleSend = async () => {
    if (!reply.trim() || sending) return
    setSending(true)
    try {
      const updated = await supportApi.addMessage(ticketUuid, reply.trim())
      setTicket(updated)
      setReply('')
    } catch {
      toast('Failed to send message', 'error')
    } finally {
      setSending(false)
    }
  }

  const handleStatusChange = async (newStatus: string) => {
    try {
      const updated = await supportApi.updateTicket(ticketUuid, { status: newStatus })
      setTicket(updated)
    } catch {
      toast('Failed to update status', 'error')
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (file.size > MAX_BYTES) {
      toast(`File must be under 10MB`, 'error')
      return
    }
    try {
      const updated = await supportApi.addAttachment(ticketUuid, file)
      setTicket(updated)
      toast('File attached', 'success')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Upload failed', 'error')
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
        <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} /> Loading ticket...
      </div>
    )
  }

  if (!ticket) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
        Ticket not found.
        <div style={{ marginTop: 12 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer' }}>
            Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900 }}>
      <button
        onClick={onBack}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px',
          border: '1px solid #d1d5db', borderRadius: 'var(--ui-radius, 12px)', background: '#fff',
          fontSize: 13, cursor: 'pointer', alignSelf: 'flex-start',
        }}
      >
        <ArrowLeft size={14} /> Back to tickets
      </button>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden', position: 'relative' }}>
        {/* Header with requester + status controls */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>{ticket.subject}</h3>
            <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
              {ticket.user_name || ticket.user_id}
              {ticket.user_email ? ` (${ticket.user_email})` : ''}
              {' · opened '}{timeAgo(ticket.created_at)}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={async () => {
                const url = `${window.location.origin}/support?ticket=${ticketUuid}`
                try {
                  await navigator.clipboard.writeText(url)
                  toast('Link copied', 'success')
                } catch {
                  toast('Could not copy link', 'error')
                }
              }}
              title="Copy shareable link to this ticket"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                fontSize: 12, padding: '4px 10px', borderRadius: 'var(--ui-radius, 12px)',
                border: '1px solid #d1d5db', background: '#fff', color: '#374151',
                cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              <Link2 size={12} /> Copy link
            </button>
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 9999,
              background: `${PRIORITY_COLORS[ticket.priority]}20`,
              color: PRIORITY_COLORS[ticket.priority],
              fontWeight: 600, textTransform: 'uppercase',
            }}>
              {ticket.priority}
            </span>
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 9999,
              background: `${STATUS_COLORS[ticket.status]}20`,
              color: STATUS_COLORS[ticket.status],
              fontWeight: 600, textTransform: 'uppercase',
            }}>
              {ticket.status.replace('_', ' ')}
            </span>
            {ticket.status !== 'closed' ? (
              <select
                value={ticket.status}
                onChange={(e) => handleStatusChange(e.target.value)}
                style={{ fontSize: 12, padding: '4px 8px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db', fontFamily: 'inherit' }}
              >
                <option value="open">Open</option>
                <option value="in_progress">In Progress</option>
                <option value="closed">Closed</option>
              </select>
            ) : (
              <button
                onClick={() => handleStatusChange('open')}
                style={{
                  fontSize: 12, padding: '4px 10px', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                Reopen
              </button>
            )}
          </div>
        </div>

        {/* Messages — agent on right (blue, "Support" label), customer on left */}
        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 520, overflowY: 'auto' }}>
          {ticket.messages.map((m) => {
            const isSupport = m.is_support_reply
            const msgAttachments = ticket.attachments.filter((a) => a.message_uuid === m.uuid)
            return (
              <div key={m.uuid} style={{ display: 'flex', flexDirection: 'column', alignItems: isSupport ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '85%', padding: '10px 14px', borderRadius: 'var(--ui-radius, 12px)',
                  background: isSupport ? '#2563eb' : '#f3f4f6',
                  color: isSupport ? '#fff' : '#111827',
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: isSupport ? 'rgba(255,255,255,0.85)' : '#6b7280' }}>
                    {m.user_name || m.user_id}
                    {isSupport && <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 500, opacity: 0.85 }}>Support</span>}
                  </div>
                  <div style={{ fontSize: 14, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                  <div style={{ fontSize: 10, marginTop: 4, color: isSupport ? 'rgba(255,255,255,0.75)' : '#9ca3af' }}>
                    {timeAgo(m.created_at)}
                  </div>
                </div>
                {msgAttachments.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6, alignItems: isSupport ? 'flex-end' : 'flex-start' }}>
                    {msgAttachments.map((a) => (
                      <AttachmentChip key={a.uuid} attachment={a} ticketUuid={ticketUuid} onPreview={setPreviewAttachment} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          {ticket.attachments.filter((a) => !a.message_uuid).length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
              {ticket.attachments.filter((a) => !a.message_uuid).map((a) => (
                <AttachmentChip key={a.uuid} attachment={a} ticketUuid={ticketUuid} onPreview={setPreviewAttachment} />
              ))}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Reply input */}
        {ticket.status !== 'closed' ? (
          <div style={{ padding: '12px 20px', borderTop: '1px solid #e5e7eb', display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={() => fileInputRef.current?.click()}
              title="Attach file"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
            >
              <Paperclip size={16} />
            </button>
            <input ref={fileInputRef} type="file" onChange={handleFileUpload} style={{ display: 'none' }} />
            <input
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder="Reply as support..."
              style={{
                flex: 1, padding: '8px 12px', fontSize: 14,
                border: '1px solid #d1d5db', borderRadius: 'var(--ui-radius, 12px)', outline: 'none',
              }}
            />
            <button
              onClick={handleSend}
              disabled={sending || !reply.trim()}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '8px 14px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600,
                cursor: reply.trim() && !sending ? 'pointer' : 'not-allowed',
                opacity: sending ? 0.6 : 1,
              }}
            >
              <Send size={14} /> {sending ? 'Sending...' : 'Reply'}
            </button>
          </div>
        ) : (
          <div style={{ padding: '12px 20px', borderTop: '1px solid #e5e7eb', fontSize: 13, color: '#6b7280', textAlign: 'center' }}>
            This ticket is closed. Reopen to send a reply.
          </div>
        )}

        {previewAttachment && (
          <div
            onClick={() => setPreviewAttachment(null)}
            style={{
              position: 'fixed', inset: 0, zIndex: 100,
              background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <div onClick={(e) => e.stopPropagation()} style={{ position: 'relative', maxWidth: '95%', maxHeight: '90%' }}>
              <button
                onClick={() => setPreviewAttachment(null)}
                style={{
                  position: 'absolute', top: -8, right: -8, padding: 6,
                  borderRadius: '50%', border: 'none', background: '#fff', cursor: 'pointer',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                }}
              >
                <X size={14} />
              </button>
              <img
                src={`/api/support/tickets/${ticketUuid}/attachments/${previewAttachment.uuid}`}
                alt={previewAttachment.filename}
                style={{ maxWidth: '100%', maxHeight: '80vh', borderRadius: 8 }}
              />
              <div style={{ marginTop: 8, textAlign: 'center', color: 'rgba(255,255,255,0.8)', fontSize: 12 }}>
                {previewAttachment.filename}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function AttachmentChip({
  attachment: a, ticketUuid, onPreview,
}: {
  attachment: SupportAttachment
  ticketUuid: string
  onPreview: (a: SupportAttachment) => void
}) {
  const [imgBroken, setImgBroken] = useState(false)
  const isImage = a.file_type?.startsWith('image/') && !imgBroken
  const downloadUrl = `/api/support/tickets/${ticketUuid}/attachments/${a.uuid}`

  if (isImage) {
    return (
      <button
        onClick={() => onPreview(a)}
        title={a.filename}
        style={{
          padding: 0, border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
          overflow: 'hidden', cursor: 'pointer', background: 'none',
        }}
      >
        <img
          src={downloadUrl}
          alt={a.filename}
          onError={() => setImgBroken(true)}
          style={{ display: 'block', maxWidth: 220, maxHeight: 160, objectFit: 'cover' }}
        />
      </button>
    )
  }

  return (
    <a
      href={downloadUrl}
      download={a.filename}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
        background: '#fff', color: '#2563eb', fontSize: 12, textDecoration: 'none',
      }}
    >
      <Paperclip size={12} />
      {a.filename}
    </a>
  )
}
