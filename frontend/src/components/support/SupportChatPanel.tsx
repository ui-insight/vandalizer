import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  Clock,
  Loader2,
  MessageSquare,
  Paperclip,
  Plus,
  Send,
  X,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../contexts/ToastContext'
import * as supportApi from '../../api/support'
import type { SupportTicket, SupportTicketSummary } from '../../types/support'

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const STATUS_DOT = {
  open: 'bg-yellow-400',
  in_progress: 'bg-blue-400',
  closed: 'bg-gray-300',
} as const

const PRIORITY_COLORS = {
  low: 'text-gray-400',
  normal: 'text-blue-500',
  high: 'text-red-500',
} as const

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

type View = 'list' | 'new' | 'chat'

function TicketListView({
  tickets,
  loading,
  isSupportAgent,
  onSelect,
  onNew,
}: {
  tickets: SupportTicketSummary[]
  loading: boolean
  isSupportAgent: boolean
  onSelect: (uuid: string) => void
  onNew: () => void
}) {
  const open = tickets.filter((t) => t.status !== 'closed')
  const closed = tickets.filter((t) => t.status === 'closed')

  // A ticket "needs attention" if the last message is from the other party
  const needsAttention = (t: SupportTicketSummary) => {
    if (!t.last_message_user_id || t.status === 'closed') return false
    if (isSupportAgent) {
      // Support agent: needs attention if last message is NOT a support reply (user is waiting)
      return t.last_message_is_support_reply === false
    }
    // Regular user: needs attention if last message IS a support reply (support responded)
    return t.last_message_is_support_reply === true
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
            <MessageSquare className="h-8 w-8 text-gray-300" />
            <p className="text-sm text-gray-500">
              {isSupportAgent ? 'No support tickets' : 'No support tickets yet'}
            </p>
            {!isSupportAgent && (
              <button
                onClick={onNew}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Create your first ticket
              </button>
            )}
          </div>
        ) : (
          <>
            {open.map((t) => {
              const attention = needsAttention(t)
              return (
                <button
                  key={t.uuid}
                  onClick={() => onSelect(t.uuid)}
                  className={`flex w-full items-start gap-3 border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50 ${
                    attention ? 'bg-blue-50/50' : ''
                  }`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[t.status]}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className={`truncate text-sm ${attention ? 'font-semibold text-gray-900' : 'font-medium text-gray-900'}`}>
                        {t.subject}
                      </p>
                      {attention && (
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      {isSupportAgent && t.user_name ? `${t.user_name}: ` : ''}
                      {t.last_message_preview || 'No messages'}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-0.5 shrink-0">
                    <span className="text-[10px] text-gray-400">{timeAgo(t.updated_at)}</span>
                    {t.message_count > 1 && (
                      <span className="text-[10px] text-gray-400">{t.message_count} msgs</span>
                    )}
                    {t.priority === 'high' && (
                      <span className="text-[10px] font-medium text-red-500">High</span>
                    )}
                  </div>
                </button>
              )
            })}
            {closed.length > 0 && (
              <details className="border-t border-gray-100">
                <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-gray-400 hover:text-gray-600">
                  {closed.length} closed ticket{closed.length !== 1 ? 's' : ''}
                </summary>
                {closed.map((t) => (
                  <button
                    key={t.uuid}
                    onClick={() => onSelect(t.uuid)}
                    className="flex w-full items-start gap-3 border-b border-gray-50 px-4 py-2.5 text-left opacity-60 hover:bg-gray-50 hover:opacity-100"
                  >
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT.closed}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-gray-700">{t.subject}</p>
                    </div>
                    <span className="text-[10px] text-gray-400">{timeAgo(t.updated_at)}</span>
                  </button>
                ))}
              </details>
            )}
          </>
        )}
      </div>

      {!isSupportAgent && tickets.length > 0 && (
        <div className="border-t p-3">
          <button
            onClick={onNew}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            New Ticket
          </button>
        </div>
      )}
    </div>
  )
}

function NewTicketView({
  onBack,
  onCreated,
}: {
  onBack: () => void
  onCreated: (ticket: SupportTicket) => void
}) {
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [priority, setPriority] = useState('normal')
  const [submitting, setSubmitting] = useState(false)
  const { toast } = useToast()

  const handleSubmit = async () => {
    if (!subject.trim() || !message.trim()) return
    setSubmitting(true)
    try {
      const ticket = await supportApi.createTicket(subject.trim(), message.trim(), priority)
      toast('Ticket created', 'success')
      onCreated(ticket)
    } catch {
      toast('Failed to create ticket', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <button onClick={onBack} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-medium text-gray-900">New Ticket</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-3 p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">Subject</label>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            placeholder="Brief summary of your issue"
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">Description</label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            placeholder="Describe your issue..."
          />
        </div>
      </div>
      <div className="border-t p-3">
        <button
          onClick={handleSubmit}
          disabled={!subject.trim() || !message.trim() || submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Submit Ticket
        </button>
      </div>
    </div>
  )
}

function ChatView({
  ticketUuid,
  isSupportAgent,
  onBack,
  onTicketUpdated,
}: {
  ticketUuid: string
  isSupportAgent: boolean
  onBack: () => void
  onTicketUpdated: () => void
}) {
  const { user } = useAuth()
  const { toast } = useToast()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [previewAttachment, setPreviewAttachment] = useState<import('../../types/support').SupportAttachment | null>(null)
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
    // Auto-clear notifications for this ticket when viewing it
    import('../../api/notifications').then(({ markReadForItem }) => {
      markReadForItem('support_ticket', ticketUuid).catch(() => {})
    })
    const interval = setInterval(loadTicket, 15000)
    return () => clearInterval(interval)
  }, [loadTicket, ticketUuid])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [ticket?.messages.length])

  const handleSend = async () => {
    if (!message.trim() || sending) return
    setSending(true)
    try {
      const updated = await supportApi.addMessage(ticketUuid, message.trim())
      setTicket(updated)
      setMessage('')
      onTicketUpdated()
    } catch {
      toast('Failed to send message', 'error')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) {
      toast('File must be under 10MB', 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1]
      try {
        const updated = await supportApi.addAttachment(ticketUuid, file.name, base64, file.type || undefined)
        setTicket(updated)
        toast('File attached', 'success')
      } catch {
        toast('Failed to upload file', 'error')
      }
    }
    reader.readAsDataURL(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleStatusChange = async (newStatus: string) => {
    setUpdatingStatus(true)
    try {
      const updated = await supportApi.updateTicket(ticketUuid, { status: newStatus })
      setTicket(updated)
      toast(`Ticket ${newStatus.replace('_', ' ')}`, 'success')
      onTicketUpdated()
    } catch {
      toast('Failed to update ticket', 'error')
    } finally {
      setUpdatingStatus(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-gray-500">
        <p className="text-sm">Ticket not found</p>
        <button onClick={onBack} className="text-xs text-blue-600 hover:underline">Back</button>
      </div>
    )
  }

  const StatusIcon = ticket.status === 'closed' ? CheckCircle2 : ticket.status === 'in_progress' ? Clock : Circle

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Chat header */}
      <div className="border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-900">{ticket.subject}</p>
            <div className="flex items-center gap-2">
              <StatusIcon className={`h-3 w-3 ${
                ticket.status === 'closed' ? 'text-gray-400' : ticket.status === 'in_progress' ? 'text-blue-500' : 'text-yellow-500'
              }`} />
              <span className="text-[10px] text-gray-400">
                {ticket.status === 'closed' ? 'Closed' : ticket.status === 'in_progress' ? 'In progress' : 'Open'}
              </span>
              {isSupportAgent && (
                <>
                  <span className="text-[10px] text-gray-300">|</span>
                  <span className={`text-[10px] font-medium ${PRIORITY_COLORS[ticket.priority]}`}>
                    {ticket.priority}
                  </span>
                  <span className="text-[10px] text-gray-300">|</span>
                  <span className="text-[10px] text-gray-400">{ticket.user_name || ticket.user_id}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Support agent ticket controls */}
        {isSupportAgent && (
          <div className="flex items-center gap-1.5 mt-2 ml-7">
            {ticket.status !== 'in_progress' && ticket.status !== 'closed' && (
              <button
                onClick={() => handleStatusChange('in_progress')}
                disabled={updatingStatus}
                className="rounded-md bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
              >
                Start Working
              </button>
            )}
            {ticket.status !== 'closed' && (
              <button
                onClick={() => handleStatusChange('closed')}
                disabled={updatingStatus}
                className="rounded-md bg-green-50 px-2.5 py-1 text-[11px] font-medium text-green-700 hover:bg-green-100 disabled:opacity-50"
              >
                Close Ticket
              </button>
            )}
            {ticket.status === 'closed' && (
              <button
                onClick={() => handleStatusChange('open')}
                disabled={updatingStatus}
                className="rounded-md bg-yellow-50 px-2.5 py-1 text-[11px] font-medium text-yellow-700 hover:bg-yellow-100 disabled:opacity-50"
              >
                Reopen
              </button>
            )}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {ticket.messages.map((msg) => {
          const isMe = msg.user_id === user?.user_id
          const msgAttachments = ticket.attachments.filter(a => a.message_uuid === msg.uuid)
          return (
            <div key={msg.uuid} className={`flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 ${
                  isMe
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                {!isMe && (
                  <p className="mb-0.5 text-[10px] font-medium text-gray-500">
                    {msg.user_name || 'Support'}
                  </p>
                )}
                <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                <p className={`mt-1 text-[10px] ${isMe ? 'text-blue-200' : 'text-gray-400'}`}>
                  {timeAgo(msg.created_at)}
                </p>
              </div>
              {msgAttachments.length > 0 && (
                <div className={`flex flex-col gap-1.5 mt-1.5 max-w-[85%] ${isMe ? 'items-end' : 'items-start'}`}>
                  {msgAttachments.map((a) => {
                    const isImage = a.file_type?.startsWith('image/')
                    const downloadUrl = `/api/support/tickets/${ticketUuid}/attachments/${a.uuid}`
                    return isImage ? (
                      <button
                        key={a.uuid}
                        onClick={() => setPreviewAttachment(a)}
                        className="block rounded-lg overflow-hidden border border-gray-200 hover:border-blue-400 transition-colors cursor-pointer"
                        title={a.filename}
                      >
                        <img
                          src={downloadUrl}
                          alt={a.filename}
                          className="max-w-[220px] max-h-[160px] object-cover"
                        />
                      </button>
                    ) : (
                      <a
                        key={a.uuid}
                        href={downloadUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs text-blue-600 border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors"
                      >
                        <Paperclip className="h-3 w-3" />
                        {a.filename}
                      </a>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
        {/* Orphan attachments (no message_uuid) */}
        {ticket.attachments.filter(a => !a.message_uuid).length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-2 border-t border-gray-100">
            {ticket.attachments.filter(a => !a.message_uuid).map((a) => {
              const isImage = a.file_type?.startsWith('image/')
              const downloadUrl = `/api/support/tickets/${ticketUuid}/attachments/${a.uuid}`
              return isImage ? (
                <button
                  key={a.uuid}
                  onClick={() => setPreviewAttachment(a)}
                  className="block rounded-lg overflow-hidden border border-gray-200 hover:border-blue-400 transition-colors cursor-pointer"
                  title={a.filename}
                >
                  <img
                    src={downloadUrl}
                    alt={a.filename}
                    className="max-w-[220px] max-h-[160px] object-cover"
                  />
                </button>
              ) : (
                <a
                  key={a.uuid}
                  href={downloadUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs text-blue-600 border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors"
                >
                  <Paperclip className="h-3 w-3" />
                  {a.filename}
                </a>
              )
            })}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Image preview lightbox */}
      {previewAttachment && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setPreviewAttachment(null)}
        >
          <div className="relative max-w-[95%] max-h-[90%]" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setPreviewAttachment(null)}
              className="absolute -top-2 -right-2 rounded-full bg-white p-1 shadow-lg text-gray-600 hover:text-gray-900"
            >
              <X className="h-4 w-4" />
            </button>
            <img
              src={`/api/support/tickets/${ticketUuid}/attachments/${previewAttachment.uuid}`}
              alt={previewAttachment.filename}
              className="max-w-full max-h-[80vh] rounded-lg shadow-2xl"
            />
            <p className="mt-2 text-center text-xs text-white/70">{previewAttachment.filename}</p>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t px-3 py-2">
        <div className="flex items-end gap-1.5">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            title="Attach file"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileUpload} />
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={ticket.status === 'closed' ? 'Reply to reopen...' : 'Type a message...'}
            rows={1}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!message.trim() || sending}
            className="rounded-lg bg-blue-600 p-1.5 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export function SupportChatPanel({
  open,
  onClose,
  initialTicket,
}: {
  open: boolean
  onClose: () => void
  initialTicket?: string
}) {
  const { user } = useAuth()
  const isSupportAgent = user?.is_support_agent ?? false

  const [view, setView] = useState<View>(initialTicket ? 'chat' : 'list')
  const [activeTicket, setActiveTicket] = useState<string | null>(initialTicket || null)
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const panelRef = useRef<HTMLDivElement>(null)

  const loadTickets = useCallback(async () => {
    try {
      const data = await supportApi.listTickets(undefined, 50)
      setTickets(data.tickets)
    } catch {
      // silent on poll
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    loadTickets()
    const interval = setInterval(loadTickets, 30000)
    return () => clearInterval(interval)
  }, [open, loadTickets])

  // Reset when opened
  useEffect(() => {
    if (open && !initialTicket) {
      setView('list')
      setActiveTicket(null)
    }
  }, [open, initialTicket])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  // Count tickets needing attention for the title bar badge
  const attentionCount = tickets.filter(t => {
    if (t.status === 'closed' || !t.last_message_user_id) return false
    return isSupportAgent
      ? t.last_message_is_support_reply === false
      : t.last_message_is_support_reply === true
  }).length

  return createPortal(
    <div
      ref={panelRef}
      className="fixed bottom-4 right-4 z-[9998] flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
      style={{ width: 380, height: 520 }}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between bg-blue-600 px-4 py-3 text-white">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="text-sm font-semibold">
            {isSupportAgent ? 'Support Center' : 'Support'}
          </span>
          {attentionCount > 0 && (
            <span className="flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-white/20 text-[10px] font-bold">
              {attentionCount}
            </span>
          )}
        </div>
        <button onClick={onClose} className="rounded p-0.5 hover:bg-blue-500">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Content area */}
      {view === 'list' && (
        <TicketListView
          tickets={tickets}
          loading={loading}
          isSupportAgent={isSupportAgent}
          onSelect={(uuid) => {
            setActiveTicket(uuid)
            setView('chat')
          }}
          onNew={() => setView('new')}
        />
      )}

      {view === 'new' && (
        <NewTicketView
          onBack={() => setView('list')}
          onCreated={(ticket) => {
            setActiveTicket(ticket.uuid)
            setView('chat')
            loadTickets()
          }}
        />
      )}

      {view === 'chat' && activeTicket && (
        <ChatView
          key={activeTicket}
          ticketUuid={activeTicket}
          isSupportAgent={isSupportAgent}
          onBack={() => {
            setView('list')
            setActiveTicket(null)
            loadTickets()
          }}
          onTicketUpdated={loadTickets}
        />
      )}
    </div>,
    document.body,
  )
}
