import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouterState } from '@tanstack/react-router'
import {
  AlertCircle,
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
import { AppLayout } from '../components/layout/AppLayout'
import { useAuth } from '../hooks/useAuth'
import { useToast } from '../contexts/ToastContext'
import * as supportApi from '../api/support'
import type {
  SupportTicket,
  SupportTicketSummary,
} from '../types/support'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const STATUS_CONFIG = {
  open: { label: 'Open', color: 'bg-yellow-100 text-yellow-800', icon: Circle },
  in_progress: { label: 'In Progress', color: 'bg-blue-100 text-blue-800', icon: Clock },
  closed: { label: 'Closed', color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
} as const

const PRIORITY_COLORS = {
  low: 'text-gray-500',
  normal: 'text-blue-600',
  high: 'text-red-600',
} as const

// ---------------------------------------------------------------------------
// New Ticket Dialog
// ---------------------------------------------------------------------------

function NewTicketDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">New Support Ticket</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Subject</label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="Brief summary of your issue"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Priority</label>
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
            <label className="mb-1 block text-sm font-medium text-gray-700">Description</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={5}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              placeholder="Describe your issue in detail..."
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!subject.trim() || !message.trim() || submitting}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            Create Ticket
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ticket Chat Panel
// ---------------------------------------------------------------------------

function TicketChat({
  ticketUuid,
  onBack,
  isSupportUser,
}: {
  ticketUuid: string
  onBack: () => void
  isSupportUser: boolean
}) {
  const { user } = useAuth()
  const { toast } = useToast()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
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
    // Poll for new messages every 15s
    const interval = setInterval(loadTicket, 15000)
    return () => clearInterval(interval)
  }, [loadTicket])

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
    // 10MB limit
    if (file.size > 10 * 1024 * 1024) {
      toast('File must be under 10MB', 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1]
      try {
        const updated = await supportApi.addAttachment(
          ticketUuid,
          file.name,
          base64,
          file.type || undefined,
        )
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
    try {
      const updated = await supportApi.updateTicket(ticketUuid, { status: newStatus })
      setTicket(updated)
      toast(`Ticket marked as ${newStatus.replace('_', ' ')}`, 'success')
    } catch {
      toast('Failed to update ticket', 'error')
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-gray-500">
        <AlertCircle className="h-8 w-8" />
        <p>Ticket not found</p>
        <button onClick={onBack} className="text-sm text-blue-600 hover:underline">
          Back to tickets
        </button>
      </div>
    )
  }

  const statusConf = STATUS_CONFIG[ticket.status]
  const StatusIcon = statusConf.icon

  return (
    <div className="flex flex-1 flex-col">
      {/* Header */}
      <div className="border-b bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">{ticket.subject}</h2>
            <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${statusConf.color}`}>
                <StatusIcon className="h-3 w-3" />
                {statusConf.label}
              </span>
              <span className={`text-xs font-medium ${PRIORITY_COLORS[ticket.priority]}`}>
                {ticket.priority.charAt(0).toUpperCase() + ticket.priority.slice(1)} priority
              </span>
              <span>by {ticket.user_name || ticket.user_id}</span>
              <span>{timeAgo(ticket.created_at)}</span>
            </div>
          </div>
          {isSupportUser && (
            <div className="flex items-center gap-2">
              {ticket.status !== 'in_progress' && ticket.status !== 'closed' && (
                <button
                  onClick={() => handleStatusChange('in_progress')}
                  className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
                >
                  Start Working
                </button>
              )}
              {ticket.status !== 'closed' && (
                <button
                  onClick={() => handleStatusChange('closed')}
                  className="rounded-lg bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100"
                >
                  Close Ticket
                </button>
              )}
              {ticket.status === 'closed' && (
                <button
                  onClick={() => handleStatusChange('open')}
                  className="rounded-lg bg-yellow-50 px-3 py-1.5 text-xs font-medium text-yellow-700 hover:bg-yellow-100"
                >
                  Reopen
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {ticket.messages.map((msg) => {
          const isMe = msg.user_id === user?.user_id
          const isSupport = msg.is_support_reply
          return (
            <div
              key={msg.uuid}
              className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[70%] rounded-xl px-4 py-3 ${
                  isMe
                    ? 'bg-blue-600 text-white'
                    : isSupport
                      ? 'bg-amber-50 border border-amber-200 text-gray-900'
                      : 'bg-gray-100 text-gray-900'
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-xs opacity-70">
                  <span className="font-medium">
                    {isMe ? 'You' : msg.user_name || msg.user_id}
                  </span>
                  {isSupport && <span className="rounded bg-amber-200 px-1 text-amber-800">Support</span>}
                  <span>{timeAgo(msg.created_at)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
              </div>
            </div>
          )
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Attachments */}
      {ticket.attachments.length > 0 && (
        <div className="border-t bg-gray-50 px-6 py-2">
          <p className="mb-1 text-xs font-medium text-gray-500">Attachments</p>
          <div className="flex flex-wrap gap-2">
            {ticket.attachments.map((a) => (
              <span
                key={a.uuid}
                className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-xs text-gray-600 border"
              >
                <Paperclip className="h-3 w-3" />
                {a.filename}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      {ticket.status !== 'closed' && (
        <div className="border-t bg-white px-6 py-3">
          <div className="flex items-end gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              title="Attach file"
            >
              <Paperclip className="h-5 w-5" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileUpload}
            />
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              rows={1}
              className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={handleSend}
              disabled={!message.trim() || sending}
              className="rounded-lg bg-blue-600 p-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {sending ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Send className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>
      )}

      {ticket.status === 'closed' && (
        <div className="border-t bg-green-50 px-6 py-3 text-center text-sm text-green-700">
          This ticket has been closed.
          {!isSupportUser && (
            <span> Send a message to reopen it.</span>
          )}
        </div>
      )}

      {/* Allow reopening by sending message even when closed */}
      {ticket.status === 'closed' && !isSupportUser && (
        <div className="border-t bg-white px-6 py-3">
          <div className="flex items-end gap-2">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Send a message to reopen this ticket..."
              rows={1}
              className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={handleSend}
              disabled={!message.trim() || sending}
              className="rounded-lg bg-blue-600 p-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {sending ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Send className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Ticket List
// ---------------------------------------------------------------------------

function TicketList({
  tickets,
  loading,
  selectedUuid,
  onSelect,
  statusFilter,
  onStatusFilterChange,
}: {
  tickets: SupportTicketSummary[]
  loading: boolean
  selectedUuid: string | null
  onSelect: (uuid: string) => void
  statusFilter: string
  onStatusFilterChange: (s: string) => void
}) {
  return (
    <div className="flex flex-col">
      {/* Filter tabs */}
      <div className="flex gap-1 border-b px-4 py-2">
        {['all', 'open', 'in_progress', 'closed'].map((s) => (
          <button
            key={s}
            onClick={() => onStatusFilterChange(s)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium ${
              statusFilter === s
                ? 'bg-blue-100 text-blue-700'
                : 'text-gray-500 hover:bg-gray-100'
            }`}
          >
            {s === 'all' ? 'All' : s === 'in_progress' ? 'In Progress' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">
            No tickets found
          </div>
        ) : (
          tickets.map((t) => {
            const conf = STATUS_CONFIG[t.status]
            const Icon = conf.icon
            return (
              <button
                key={t.uuid}
                onClick={() => onSelect(t.uuid)}
                className={`w-full border-b px-4 py-3 text-left hover:bg-gray-50 ${
                  selectedUuid === t.uuid ? 'bg-blue-50' : ''
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-gray-900">
                      {t.subject}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-gray-500">
                      {t.user_name || t.user_id}
                      {t.last_message_preview && ` — ${t.last_message_preview}`}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${conf.color}`}>
                      <Icon className="h-2.5 w-2.5" />
                      {conf.label}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      {timeAgo(t.updated_at || t.created_at)}
                    </span>
                    {t.message_count > 1 && (
                      <span className="flex items-center gap-0.5 text-[10px] text-gray-400">
                        <MessageSquare className="h-2.5 w-2.5" />
                        {t.message_count}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function Support() {
  const { user } = useAuth()
  const { toast } = useToast()
  const search = useRouterState({ select: (s) => s.location.search }) as { ticket?: string }

  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedTicket, setSelectedTicket] = useState<string | null>(null)
  const [showNewTicket, setShowNewTicket] = useState(false)
  const [isSupportUser, setIsSupportUser] = useState(false)

  // Check if user is support staff
  useEffect(() => {
    if (user?.is_admin) {
      setIsSupportUser(true)
      return
    }
    supportApi.getSupportContacts()
      .then(() => setIsSupportUser(true))
      .catch(() => setIsSupportUser(false))
  }, [user])

  // Check URL for pre-selected ticket
  useEffect(() => {
    if (search?.ticket) setSelectedTicket(search.ticket)
  }, [search])

  const loadTickets = useCallback(async () => {
    try {
      const status = statusFilter === 'all' ? undefined : statusFilter
      const data = await supportApi.listTickets(status)
      setTickets(data.tickets)
    } catch {
      toast('Failed to load tickets', 'error')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, toast])

  useEffect(() => {
    loadTickets()
    const interval = setInterval(loadTickets, 30000)
    return () => clearInterval(interval)
  }, [loadTickets])

  const handleTicketCreated = (ticket: SupportTicket) => {
    setShowNewTicket(false)
    setSelectedTicket(ticket.uuid)
    loadTickets()
  }

  return (
    <AppLayout>
      <div className="flex h-full">
        {/* Left: ticket list */}
        <div className="flex w-80 flex-col border-r bg-white">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <h1 className="text-base font-semibold text-gray-900">
              {isSupportUser ? 'Support Center' : 'Support'}
            </h1>
            <button
              onClick={() => setShowNewTicket(true)}
              className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              New Ticket
            </button>
          </div>
          <TicketList
            tickets={tickets}
            loading={loading}
            selectedUuid={selectedTicket}
            onSelect={setSelectedTicket}
            statusFilter={statusFilter}
            onStatusFilterChange={(s) => {
              setStatusFilter(s)
              setLoading(true)
            }}
          />
        </div>

        {/* Right: chat or empty state */}
        <div className="flex flex-1 flex-col bg-white">
          {selectedTicket ? (
            <TicketChat
              key={selectedTicket}
              ticketUuid={selectedTicket}
              onBack={() => setSelectedTicket(null)}
              isSupportUser={isSupportUser}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-gray-400">
              <MessageSquare className="h-12 w-12" />
              <p className="text-sm">Select a ticket or create a new one</p>
            </div>
          )}
        </div>
      </div>

      {showNewTicket && (
        <NewTicketDialog
          onClose={() => setShowNewTicket(false)}
          onCreated={handleTicketCreated}
        />
      )}
    </AppLayout>
  )
}
