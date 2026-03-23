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
  Send,
} from 'lucide-react'
import { AppLayout } from '../components/layout/AppLayout'
import { useToast } from '../contexts/ToastContext'
import * as supportApi from '../api/support'
import type { SupportTicket, SupportTicketSummary } from '../types/support'

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
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
// Ticket Chat (staff view with management controls)
// ---------------------------------------------------------------------------

function TicketChat({
  ticketUuid,
  onBack,
  onUpdated,
}: {
  ticketUuid: string
  onBack: () => void
  onUpdated: () => void
}) {
  const { toast } = useToast()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadTicket = useCallback(async () => {
    try {
      setTicket(await supportApi.getTicket(ticketUuid))
    } catch {
      toast('Failed to load ticket', 'error')
    } finally {
      setLoading(false)
    }
  }, [ticketUuid, toast])

  useEffect(() => {
    loadTicket()
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
      setTicket(await supportApi.addMessage(ticketUuid, message.trim()))
      setMessage('')
    } catch {
      toast('Failed to send message', 'error')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { toast('File must be under 10MB', 'error'); return }
    const reader = new FileReader()
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1]
      try {
        setTicket(await supportApi.addAttachment(ticketUuid, file.name, base64, file.type || undefined))
        toast('File attached', 'success')
      } catch { toast('Failed to upload file', 'error') }
    }
    reader.readAsDataURL(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleStatus = async (s: string) => {
    try {
      setTicket(await supportApi.updateTicket(ticketUuid, { status: s }))
      toast(`Ticket ${s.replace('_', ' ')}`, 'success')
      onUpdated()
    } catch { toast('Failed to update', 'error') }
  }

  if (loading) return <div className="flex flex-1 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
  if (!ticket) return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-gray-500">
      <AlertCircle className="h-8 w-8" /><p>Ticket not found</p>
      <button onClick={onBack} className="text-sm text-blue-600 hover:underline">Back</button>
    </div>
  )

  const sc = STATUS_CONFIG[ticket.status]
  const SI = sc.icon

  return (
    <div className="flex flex-1 flex-col">
      {/* Header */}
      <div className="border-b bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 lg:hidden">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-gray-900 truncate">{ticket.subject}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-gray-500">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${sc.color}`}>
                <SI className="h-3 w-3" />{sc.label}
              </span>
              <span className={`text-xs font-medium ${PRIORITY_COLORS[ticket.priority]}`}>
                {ticket.priority.charAt(0).toUpperCase() + ticket.priority.slice(1)}
              </span>
              <span>{ticket.user_name || ticket.user_id}</span>
              {ticket.user_email && <span className="text-xs text-gray-400">{ticket.user_email}</span>}
              <span>{timeAgo(ticket.created_at)}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {ticket.status !== 'in_progress' && ticket.status !== 'closed' && (
              <button onClick={() => handleStatus('in_progress')} className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100">Start Working</button>
            )}
            {ticket.status !== 'closed' && (
              <button onClick={() => handleStatus('closed')} className="rounded-lg bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100">Close</button>
            )}
            {ticket.status === 'closed' && (
              <button onClick={() => handleStatus('open')} className="rounded-lg bg-yellow-50 px-3 py-1.5 text-xs font-medium text-yellow-700 hover:bg-yellow-100">Reopen</button>
            )}
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {ticket.messages.map((msg) => {
          const isStaff = msg.is_support_reply
          return (
            <div key={msg.uuid} className={`flex ${isStaff ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] rounded-xl px-4 py-3 ${
                isStaff ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900'
              }`}>
                <div className="mb-1 flex items-center gap-2 text-xs opacity-70">
                  <span className="font-medium">{msg.user_name || msg.user_id}</span>
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
          <div className="flex flex-wrap gap-2">
            {ticket.attachments.map((a) => (
              <span key={a.uuid} className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-xs text-gray-600 border">
                <Paperclip className="h-3 w-3" />{a.filename}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t bg-white px-6 py-3">
        <div className="flex items-end gap-2">
          <button onClick={() => fileInputRef.current?.click()} className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600" title="Attach file">
            <Paperclip className="h-5 w-5" />
          </button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileUpload} />
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Reply as support..."
            rows={1}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button onClick={handleSend} disabled={!message.trim() || sending} className="rounded-lg bg-blue-600 p-2 text-white hover:bg-blue-700 disabled:opacity-50">
            {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Support Center Page
// ---------------------------------------------------------------------------

export default function Support() {
  const { toast } = useToast()
  const search = useRouterState({ select: (s) => s.location.search }) as { ticket?: string }

  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedTicket, setSelectedTicket] = useState<string | null>(search?.ticket || null)

  const loadTickets = useCallback(async () => {
    try {
      const status = statusFilter === 'all' ? undefined : statusFilter
      setTickets((await supportApi.listTickets(status)).tickets)
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

  const counts = {
    all: tickets.length,
    open: tickets.filter((t) => t.status === 'open').length,
    in_progress: tickets.filter((t) => t.status === 'in_progress').length,
    closed: tickets.filter((t) => t.status === 'closed').length,
  }

  return (
    <AppLayout>
      <div className="flex h-full">
        {/* Left: ticket list */}
        <div className={`flex w-80 flex-col border-r bg-white ${selectedTicket ? 'hidden lg:flex' : 'flex'}`}>
          <div className="border-b px-4 py-3">
            <h1 className="text-base font-semibold text-gray-900">Support Center</h1>
            <p className="text-xs text-gray-500 mt-0.5">{counts.open + counts.in_progress} open ticket{counts.open + counts.in_progress !== 1 ? 's' : ''}</p>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-1 border-b px-3 py-2">
            {(['all', 'open', 'in_progress', 'closed'] as const).map((s) => (
              <button
                key={s}
                onClick={() => { setStatusFilter(s); setLoading(true) }}
                className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                  statusFilter === s ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                {s === 'all' ? 'All' : s === 'in_progress' ? 'Active' : s.charAt(0).toUpperCase() + s.slice(1)}
                <span className="ml-1 text-[10px] opacity-60">{counts[s]}</span>
              </button>
            ))}
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-gray-400" /></div>
            ) : tickets.length === 0 ? (
              <div className="py-12 text-center text-sm text-gray-400">No tickets</div>
            ) : (
              tickets.map((t) => {
                const c = STATUS_CONFIG[t.status]
                const I = c.icon
                return (
                  <button
                    key={t.uuid}
                    onClick={() => setSelectedTicket(t.uuid)}
                    className={`w-full border-b px-4 py-3 text-left hover:bg-gray-50 ${selectedTicket === t.uuid ? 'bg-blue-50' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-gray-900">{t.subject}</p>
                        <p className="mt-0.5 truncate text-xs text-gray-500">{t.user_name || t.user_id} — {t.last_message_preview || 'No messages'}</p>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${c.color}`}>
                          <I className="h-2.5 w-2.5" />{c.label}
                        </span>
                        <span className="text-[10px] text-gray-400">{timeAgo(t.updated_at || t.created_at)}</span>
                        {t.message_count > 1 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-gray-400">
                            <MessageSquare className="h-2.5 w-2.5" />{t.message_count}
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

        {/* Right: chat or empty state */}
        <div className={`flex flex-1 flex-col bg-white ${selectedTicket ? 'flex' : 'hidden lg:flex'}`}>
          {selectedTicket ? (
            <TicketChat
              key={selectedTicket}
              ticketUuid={selectedTicket}
              onBack={() => setSelectedTicket(null)}
              onUpdated={loadTickets}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-gray-400">
              <MessageSquare className="h-12 w-12" />
              <p className="text-sm">Select a ticket to respond</p>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
