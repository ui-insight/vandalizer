import { useEffect, useState, useCallback, useRef } from 'react'
import { Navigate, useNavigate, useSearch } from '@tanstack/react-router'
import {
  ArrowLeft, MessageSquare, Send, Plus, Paperclip, X, Loader2,
  CheckCircle2, Clock, Circle,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import { openSupportPanel } from '../utils/supportPanel'
import * as supportApi from '../api/support'
import type {
  SupportTicket, SupportTicketSummary, SupportAttachment,
} from '../types/support'

type View = 'list' | 'new' | 'chat'

const MAX_BYTES = 10 * 1024 * 1024

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const STATUS_BG: Record<string, string> = {
  open: '#fef3c7',
  in_progress: '#dbeafe',
  closed: '#f3f4f6',
}
const STATUS_FG: Record<string, string> = {
  open: '#b45309',
  in_progress: '#1d4ed8',
  closed: '#6b7280',
}

export default function SupportCenter() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const search = useSearch({ from: '/support' }) as { ticket?: string }
  const { toast } = useToast()

  const [view, setView] = useState<View>('list')
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTicketUuid, setActiveTicketUuid] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await supportApi.listTickets(undefined, 100, 0, 'mine')
      setTickets(data.tickets)
    } catch {
      toast('Failed to load tickets', 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  // Deep link: /support?ticket=X. If the ticket is mine, open it in chat view.
  // If it isn't (i.e., a notification points at a queue item), hand off to the
  // answering panel and clear the URL param so the page doesn't keep retrying.
  useEffect(() => {
    if (!search.ticket || !user) return
    const uuid = search.ticket
    supportApi.getTicket(uuid).then((t) => {
      if (t.user_id === user.user_id) {
        setActiveTicketUuid(uuid)
        setView('chat')
      } else {
        openSupportPanel(uuid)
        navigate({ to: '/support', search: { ticket: undefined } })
      }
    }).catch(() => { /* not found / not authorized — ignore */ })
  }, [search.ticket, user, navigate])

  if (!user?.is_support_agent) {
    return <Navigate to="/" search={{ mode: undefined, tab: undefined, workflow: undefined, extraction: undefined, automation: undefined, kb: undefined }} />
  }

  const openTicket = (uuid: string) => {
    setActiveTicketUuid(uuid)
    setView('chat')
  }

  const backToList = () => {
    setActiveTicketUuid(null)
    setView('list')
    load()
  }

  return (
    <PageLayout>
      {view === 'list' && (
        <ListView
          tickets={tickets}
          loading={loading}
          onNew={() => setView('new')}
          onSelect={openTicket}
        />
      )}
      {view === 'new' && (
        <NewTicketView
          onBack={() => setView('list')}
          onCreated={(t) => {
            setActiveTicketUuid(t.uuid)
            setView('chat')
            load()
          }}
        />
      )}
      {view === 'chat' && activeTicketUuid && (
        <ChatView
          ticketUuid={activeTicketUuid}
          onBack={backToList}
        />
      )}
    </PageLayout>
  )
}

// ---------------------------------------------------------------------------
// List view — my tickets + prominent New Ticket CTA
// ---------------------------------------------------------------------------

function ListView({
  tickets, loading, onNew, onSelect,
}: {
  tickets: SupportTicketSummary[]
  loading: boolean
  onNew: () => void
  onSelect: (uuid: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <MessageSquare size={20} color="#6b7280" />
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Support Center</h1>
            <p style={{ margin: '2px 0 0', fontSize: 13, color: '#6b7280' }}>
              File your own tickets and run QA against the support workflow. The answering queue lives in the floating Support panel.
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

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 14, fontWeight: 600 }}>
          My Tickets
        </div>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
            <Loader2 size={20} style={{ display: 'inline-block', animation: 'spin 1s linear infinite', verticalAlign: 'middle' }} />
            <span style={{ marginLeft: 8 }}>Loading...</span>
          </div>
        ) : tickets.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
            <MessageSquare size={28} color="#d1d5db" style={{ display: 'block', margin: '0 auto 8px' }} />
            <div style={{ fontSize: 14, marginBottom: 12 }}>You haven&rsquo;t filed any tickets.</div>
            <button
              onClick={onNew}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '8px 14px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              }}
            >
              <Plus size={14} /> File your first ticket
            </button>
          </div>
        ) : (
          <div>
            {tickets.map((t) => (
              <button
                key={t.uuid}
                onClick={() => onSelect(t.uuid)}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  width: '100%', padding: '12px 20px', borderBottom: '1px solid #f3f4f6',
                  background: '#fff', border: 'none', borderTop: 'none', borderLeft: 'none', borderRight: 'none',
                  cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#f9fafb' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = '#fff' }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.subject}
                    </span>
                    <span style={{
                      fontSize: 11, padding: '1px 6px', borderRadius: 9999,
                      background: STATUS_BG[t.status], color: STATUS_FG[t.status], fontWeight: 600,
                    }}>
                      {t.status.replace('_', ' ')}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.message_count} message{t.message_count !== 1 ? 's' : ''}
                    {t.last_message_preview ? ` — ${t.last_message_preview}` : ''}
                  </div>
                </div>
                <div style={{ fontSize: 12, color: '#9ca3af', flexShrink: 0, marginLeft: 16 }}>
                  {timeAgo(t.updated_at || t.created_at)}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// New ticket form
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
        <ArrowLeft size={14} /> Back to my tickets
      </button>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 24 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700 }}>File a Ticket</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: '#6b7280' }}>
          Tickets you create here go into the same queue your team answers from.
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
// Chat view — customer mode (no status controls, no agent badges)
// ---------------------------------------------------------------------------

function ChatView({
  ticketUuid, onBack,
}: {
  ticketUuid: string
  onBack: () => void
}) {
  const { user } = useAuth()
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

  const StatusIcon = ticket.status === 'closed' ? CheckCircle2 : ticket.status === 'in_progress' ? Clock : Circle
  const statusColor = ticket.status === 'closed' ? '#9ca3af' : ticket.status === 'in_progress' ? '#3b82f6' : '#f59e0b'

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
        <ArrowLeft size={14} /> Back to my tickets
      </button>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden', position: 'relative' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>{ticket.subject}</h3>
            <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <StatusIcon size={12} color={statusColor} />
              <span style={{ textTransform: 'capitalize' }}>{ticket.status.replace('_', ' ')}</span>
              <span>&middot; opened {timeAgo(ticket.created_at)}</span>
            </div>
          </div>
        </div>

        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12, maxHeight: 520, overflowY: 'auto' }}>
          {ticket.messages.map((m) => {
            const isMine = m.user_id === user?.user_id
            const msgAttachments = ticket.attachments.filter((a) => a.message_uuid === m.uuid)
            return (
              <div key={m.uuid} style={{ display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '85%', padding: '10px 14px', borderRadius: 'var(--ui-radius, 12px)',
                  background: isMine ? '#2563eb' : '#f3f4f6',
                  color: isMine ? '#fff' : '#111827',
                }}>
                  {!isMine && (
                    <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 4 }}>
                      {m.user_name || 'Support'}
                    </div>
                  )}
                  <div style={{ fontSize: 14, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                  <div style={{ fontSize: 10, marginTop: 4, color: isMine ? 'rgba(255,255,255,0.75)' : '#9ca3af' }}>
                    {timeAgo(m.created_at)}
                  </div>
                </div>
                {msgAttachments.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6, alignItems: isMine ? 'flex-end' : 'flex-start' }}>
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

        {ticket.status !== 'closed' && (
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
              placeholder="Type a reply..."
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
        )}
        {ticket.status === 'closed' && (
          <div style={{ padding: '12px 20px', borderTop: '1px solid #e5e7eb', fontSize: 13, color: '#6b7280', textAlign: 'center' }}>
            This ticket is closed. An agent can reopen it from the Support panel.
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
