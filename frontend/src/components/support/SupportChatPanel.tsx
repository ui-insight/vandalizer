import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { createPortal } from '../shared/panelPortal'
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Circle,
  Clock,
  Eye,
  Heart,
  Loader2,
  Lock,
  MessageSquare,
  Paperclip,
  Pencil,
  Plus,
  Send,
  Sparkles,
  Trash2,
  Upload,
  UserPlus,
  X,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../contexts/ToastContext'
import { useConfirm } from '../shared/useConfirm'
import * as supportApi from '../../api/support'
import { submitProductFeedback } from '../../api/feedback'
import type { SupportTicket, SupportTicketSummary } from '../../types/support'
import type { SupportDraftContext } from '../../utils/supportPanel'

const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

// Drag-and-drop file handling for the support panel.
//
// The app installs a global drop guard on `document` (see App.tsx) that cancels
// any OS file drop landing outside a real drop zone. The support panel is also
// rendered through a portal to document.body, so it sits outside the React root.
// Both facts mean React synthetic onDrop handlers are unreliable here: to claim a
// drop we must attach NATIVE listeners on the zone element and stopPropagation so
// the event never bubbles up to the global guard.
//
// We attach via a CALLBACK ref rather than useEffect+ref: the zone lives behind
// early returns (the chat view renders a loading spinner first), so a mount-time
// effect would see a null node and never re-run once the real zone appears. A
// callback ref fires whenever the node actually mounts/unmounts, so listeners
// always land on the live element. `onFiles` is read through a ref to keep the
// callback identity stable (no detach/reattach on every render).
function useFileDropZone(onFiles: (files: File[]) => void) {
  const [dragOver, setDragOver] = useState(false)
  const depth = useRef(0)
  const onFilesRef = useRef(onFiles)
  onFilesRef.current = onFiles
  const cleanupRef = useRef<(() => void) | null>(null)

  const dropRef = useCallback((el: HTMLElement | null) => {
    // Detach from any previously held node before (re)wiring.
    if (cleanupRef.current) {
      cleanupRef.current()
      cleanupRef.current = null
    }
    if (!el) return
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files')

    const onDragEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      depth.current++
      setDragOver(true)
    }
    const onDragOver = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    }
    const onDragLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      depth.current--
      if (depth.current <= 0) {
        depth.current = 0
        setDragOver(false)
      }
    }
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      e.stopPropagation()
      depth.current = 0
      setDragOver(false)
      if (e.dataTransfer) onFilesRef.current(Array.from(e.dataTransfer.files))
    }

    el.addEventListener('dragenter', onDragEnter)
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    cleanupRef.current = () => {
      el.removeEventListener('dragenter', onDragEnter)
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [])

  return { dragOver, dropRef }
}

function DropOverlay({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div className="pointer-events-none absolute inset-0 z-50 m-2 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-blue-400 bg-blue-50/90">
      <Upload className="h-7 w-7 text-blue-500" />
      <p className="text-sm font-medium text-blue-600">Drop files to attach</p>
    </div>
  )
}

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
  low: 'text-gray-500',
  normal: 'text-blue-700',
  high: 'text-red-700',
} as const

const CLASSIFICATION_LABELS = {
  bug: 'Bug',
  enhancement: 'Enhancement',
  feature_request: 'Feature Request',
} as const

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

type View = 'list' | 'new' | 'chat' | 'praise'

function TicketListView({
  tickets,
  loading,
  isSupportAgent,
  currentUserId,
  onSelect,
  onNew,
  onPraise,
}: {
  tickets: SupportTicketSummary[]
  loading: boolean
  isSupportAgent: boolean
  currentUserId: string
  onSelect: (uuid: string) => void
  onNew: () => void
  onPraise: () => void
}) {
  const open = tickets.filter((t) => t.status !== 'closed')
  const closed = tickets.filter((t) => t.status === 'closed')

  // A ticket "needs attention" if the last message is from the other party
  // AND the current user hasn't read it yet (server-side tracking via read_by).
  const needsAttention = (t: SupportTicketSummary) => {
    if (!t.last_message_user_id || t.status === 'closed') return false
    const isNew = isSupportAgent
      ? t.last_message_is_support_reply === false
      : t.last_message_is_support_reply === true
    if (!isNew) return false
    // Server tracks who has read each ticket since the last message
    if (t.read_by?.includes(currentUserId)) return false
    return true
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-600" />
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
                className="rounded-lg bg-highlight px-4 py-2 text-sm font-semibold text-highlight-text hover:brightness-90"
              >
                Create your first ticket
              </button>
            )}
          </div>
        ) : (
          <>
            {open.map((t) => {
              const attention = needsAttention(t)
              const isWatching = t.user_id !== currentUserId
                && (t.watcher_ids ?? []).includes(currentUserId)
              return (
                // Not a <button>: browsers block text selection inside buttons,
                // and users need to copy the subject/preview text from the row.
                <div
                  key={t.uuid}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    if (window.getSelection()?.toString()) return
                    onSelect(t.uuid)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(t.uuid)
                    }
                  }}
                  className={`flex w-full cursor-pointer items-start gap-3 border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50 ${
                    attention ? 'bg-blue-50/50' : ''
                  }`}
                >
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[t.status]}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      {t.category === 'feedback_prompt' && (
                        <span className="shrink-0 rounded bg-amber-100 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-700">
                          Check-in
                        </span>
                      )}
                      {isWatching && (
                        <span
                          className="shrink-0 inline-flex items-center gap-0.5 rounded bg-indigo-50 px-1 py-0.5 text-[9px] font-bold uppercase text-indigo-700"
                          title="You were tagged on this ticket"
                        >
                          <Eye className="h-2.5 w-2.5" />
                          Watching
                        </span>
                      )}
                      <p className={`truncate text-sm ${attention ? 'font-semibold text-gray-900' : 'font-medium text-gray-900'}`}>
                        {t.ticket_number != null && (
                          <span className="mr-1 font-mono text-[11px] text-gray-500">#{t.ticket_number}</span>
                        )}
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
                    <span className="text-[10px] text-gray-500">{timeAgo(t.updated_at)}</span>
                    {t.message_count > 1 && (
                      <span className="text-[10px] text-gray-500">{t.message_count} msgs</span>
                    )}
                    {t.priority === 'high' && (
                      <span className="text-[10px] font-medium text-red-500">High</span>
                    )}
                  </div>
                </div>
              )
            })}
            {closed.length > 0 && (
              <details className="border-t border-gray-100">
                <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-gray-500 hover:text-gray-600">
                  {closed.length} closed ticket{closed.length !== 1 ? 's' : ''}
                </summary>
                {closed.map((t) => (
                  <div
                    key={t.uuid}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      if (window.getSelection()?.toString()) return
                      onSelect(t.uuid)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onSelect(t.uuid)
                      }
                    }}
                    className="flex w-full cursor-pointer items-start gap-3 border-b border-gray-50 px-4 py-2.5 text-left opacity-60 hover:bg-gray-50 hover:opacity-100"
                  >
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${STATUS_DOT.closed}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-gray-700">
                        {t.ticket_number != null && (
                          <span className="mr-1 font-mono text-[11px] text-gray-500">#{t.ticket_number}</span>
                        )}
                        {t.subject}
                      </p>
                    </div>
                    <span className="text-[10px] text-gray-500">{timeAgo(t.updated_at)}</span>
                  </div>
                ))}
              </details>
            )}
          </>
        )}
      </div>

      {!isSupportAgent && (
        <div className="space-y-2 border-t p-3">
          {tickets.length > 0 && (
            <button
              onClick={onNew}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-highlight px-3 py-2 text-sm font-semibold text-highlight-text hover:brightness-90"
            >
              <Plus className="h-4 w-4" />
              New Ticket
            </button>
          )}
          <button
            onClick={onPraise}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-pink-200 bg-pink-50 px-3 py-2 text-sm font-medium text-pink-700 hover:bg-pink-100"
          >
            <Heart className="h-4 w-4" />
            Something working well?
          </button>
        </div>
      )}
    </div>
  )
}

// Off-ticket positive feedback. Deliberately NOT a support ticket: praise and
// ideas shouldn't enter the triage queue or fire the ticket notification
// fan-out. Writes to ProductFeedback and surfaces in the "What's Working" feed.
function PraiseView({ onBack }: { onBack: () => void }) {
  const [sentiment, setSentiment] = useState<'positive' | 'idea'>('positive')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const { toast } = useToast()

  const handleSubmit = async () => {
    if (!message.trim()) return
    setSubmitting(true)
    try {
      await submitProductFeedback({
        message: message.trim(),
        sentiment,
        source: 'support_panel',
      })
      setSent(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to send feedback'
      toast(msg, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="flex items-center gap-2 border-b px-4 py-2">
          <span className="text-sm font-medium text-gray-900">Thank you</span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <Heart className="h-10 w-10 text-pink-500" />
          <p className="text-sm font-medium text-gray-900">This makes our day.</p>
          <p className="text-xs text-gray-500">
            Thanks for taking a moment to tell us what&rsquo;s working — it genuinely helps.
          </p>
          <button
            onClick={onBack}
            className="mt-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
          >
            Done
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <button type="button" onClick={onBack} aria-label="Back" className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-medium text-gray-900">Share what&rsquo;s working</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-3 p-4">
        <p className="text-xs text-gray-500">
          Something you love, or an idea to make it even better? We&rsquo;d love to hear it — this
          isn&rsquo;t a ticket, just a note to the team.
        </p>
        <div className="flex gap-2">
          {([['positive', 'Something I love'], ['idea', 'An idea']] as const).map(([val, label]) => {
            const active = sentiment === val
            return (
              <button
                key={val}
                type="button"
                onClick={() => setSentiment(val)}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium ${
                  active
                    ? 'border-pink-300 bg-pink-50 text-pink-700'
                    : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                {val === 'positive' ? <Heart className="mr-1 inline h-3.5 w-3.5" /> : <Sparkles className="mr-1 inline h-3.5 w-3.5" />}
                {label}
              </button>
            )
          })}
        </div>
        <textarea
          aria-label="Feedback message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={5}
          autoFocus
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-pink-400 focus:outline-none focus:ring-2 focus:ring-pink-300"
          placeholder={sentiment === 'positive'
            ? 'What worked well for you?'
            : 'What would make Vandalizer better?'}
        />
      </div>
      <div className="border-t p-3">
        <button
          onClick={handleSubmit}
          disabled={submitting || !message.trim()}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-pink-600 px-3 py-2 text-sm font-medium text-white hover:bg-pink-700 disabled:opacity-50"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Heart className="h-4 w-4" />}
          Send
        </button>
      </div>
    </div>
  )
}

type TicketDraft = { subject: string; message: string; priority: string; classification: string; files: File[] }
const emptyTicketDraft = (): TicketDraft => ({ subject: '', message: '', priority: 'normal', classification: 'bug', files: [] })

function NewTicketView({
  onBack,
  onCreated,
  draft,
  setDraft,
  submitting,
  setSubmitting,
}: {
  onBack: () => void
  onCreated: (ticket: SupportTicket) => void
  submitting: boolean
  setSubmitting: (pending: boolean) => void
  draft: TicketDraft
  setDraft: Dispatch<SetStateAction<TicketDraft>>
}) {
  const { subject, message, priority, classification, files } = draft
  const setSubject = (subject: string) => setDraft(d => ({ ...d, subject }))
  const setMessage = (message: string) => setDraft(d => ({ ...d, message }))
  const setPriority = (priority: string) => setDraft(d => ({ ...d, priority }))
  const setClassification = (classification: string) => setDraft(d => ({ ...d, classification }))
  const setFiles = useCallback((next: SetStateAction<File[]>) => setDraft(d => ({ ...d, files: typeof next === 'function' ? next(d.files) : next })), [setDraft])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const acceptFiles = useCallback((picked: File[]) => {
    const accepted: File[] = []
    for (const f of picked) {
      if (f.size > MAX_ATTACHMENT_BYTES) {
        toast(`${f.name} is over 10MB`, 'error')
        continue
      }
      accepted.push(f)
    }
    if (accepted.length) setFiles((prev) => [...prev, ...accepted])
  }, [toast, setFiles])

  const { dragOver, dropRef } = useFileDropZone(acceptFiles)

  const handleFilesPicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ''
    acceptFiles(picked)
  }

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  const handleSubmit = async () => {
    if (submitting || !subject.trim() || !message.trim()) return
    setSubmitting(true)
    try {
      const ticket = await supportApi.createTicket(
        subject.trim(),
        message.trim(),
        priority,
        classification,
        files,
      )
      toast('Ticket created', 'success')
      onCreated(ticket)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create ticket'
      toast(msg, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div ref={dropRef} className="relative flex flex-1 flex-col overflow-hidden">
      <DropOverlay show={dragOver} />
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <button type="button" onClick={onBack} aria-label="Back" className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="text-sm font-medium text-gray-900">New Ticket</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-3 p-4">
        <p className="text-sm text-gray-600">Describe what happened and what you expected. Your description and attachments go to Support; reopen this panel to read replies.</p>
        <div>
          <label htmlFor="support-new-subject" className="mb-1 block text-xs font-medium text-gray-600">Subject</label>
          <input
            id="support-new-subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Brief summary — a problem, or something you'd like"
            autoFocus
          />
        </div>
        <div>
          <label htmlFor="support-new-description" className="mb-1 block text-xs font-medium text-gray-600">Description</label>
          <textarea
            id="support-new-description"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Tell us what's happening, or what you'd like to see..."
          />
        </div>
        <details className="rounded-lg border border-gray-200 p-3">
          <summary className="cursor-pointer text-sm font-medium">Ticket options · normal priority by default</summary>
          <div className="mt-3 space-y-3">
        <div>
          <label htmlFor="support-new-priority" className="mb-1 block text-xs font-medium text-gray-600">Priority</label>
          <select
            id="support-new-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </div>
        <div>
          <label htmlFor="support-new-classification" className="mb-1 block text-xs font-medium text-gray-600">Type</label>
          <select
            id="support-new-classification"
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="bug">Bug</option>
            <option value="enhancement">Enhancement</option>
            <option value="feature_request">Feature Request</option>
          </select>
        </div>
          </div>
        </details>
        <div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-gray-600">Attachments</label>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1 rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600"
              title="Attach file"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              aria-label="Upload files"
              className="hidden"
              onChange={handleFilesPicked}
            />
          </div>
          {files.length > 0 && (
            <ul className="mt-1 space-y-1">
              {files.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs"
                >
                  <span className="truncate text-gray-700" title={f.name}>{f.name}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    className="shrink-0 rounded p-0.5 text-gray-600 hover:bg-gray-200 hover:text-gray-600"
                    title="Remove"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="border-t p-3">
        <button
          onClick={handleSubmit}
          disabled={!subject.trim() || !message.trim() || submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-highlight px-3 py-2 text-sm font-semibold text-highlight-text hover:brightness-90 disabled:opacity-50"
        >
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Submit Ticket
        </button>
      </div>
    </div>
  )
}

function AttachmentChip({
  attachment: a,
  ticketUuid,
  onPreview,
  onDelete,
}: {
  attachment: import('../../types/support').SupportAttachment
  ticketUuid: string
  onPreview: (a: import('../../types/support').SupportAttachment) => void
  onDelete?: () => void
}) {
  const [imgBroken, setImgBroken] = useState(false)
  const isImage = a.file_type?.startsWith('image/') && !imgBroken
  const downloadUrl = `/api/support/tickets/${ticketUuid}/attachments/${a.uuid}`

  const removeButton = onDelete && (
    <button
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); onDelete() }}
      title="Remove attachment"
      className="absolute -top-1.5 -right-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-sm hover:text-red-600"
    >
      <X className="h-3 w-3" />
    </button>
  )

  if (isImage) {
    return (
      <div className="relative inline-block">
        <button
          onClick={() => onPreview(a)}
          className="block rounded-lg overflow-hidden border border-gray-200 hover:border-blue-400 transition-colors cursor-pointer"
          title={a.filename}
        >
          <img
            src={downloadUrl}
            alt={a.filename}
            className="max-w-[220px] max-h-[160px] object-cover"
            onError={() => setImgBroken(true)}
          />
        </button>
        {removeButton}
      </div>
    )
  }

  return (
    <div className="relative inline-block">
      <a
        href={downloadUrl}
        download={a.filename}
        className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-xs text-blue-600 border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors"
      >
        <Paperclip className="h-3 w-3" />
        {a.filename}
      </a>
      {removeButton}
    </div>
  )
}

type ReplyDraft = { message: string; isInternalNote: boolean; failedFiles: File[]; sending: boolean; uploading: boolean }
const emptyReplyDraft = (): ReplyDraft => ({ message: '', isInternalNote: false, failedFiles: [], sending: false, uploading: false })

function ChatView({
  ticketUuid,
  draft,
  setDraft,
  isSupportAgent,
  onBack,
  onTicketUpdated,
  onDismissPrompt,
}: {
  ticketUuid: string
  draft: ReplyDraft
  setDraft: Dispatch<SetStateAction<ReplyDraft>>
  isSupportAgent: boolean
  onBack: () => void
  onTicketUpdated: () => void
  onDismissPrompt?: () => void
}) {
  const { user } = useAuth()
  const { toast } = useToast()
  const confirm = useConfirm()
  const [ticket, setTicket] = useState<SupportTicket | null>(null)
  const [loading, setLoading] = useState(true)
  const { message, isInternalNote, sending, uploading, failedFiles } = draft
  const setMessage = (message: string) => setDraft(d => ({ ...d, message }))
  const setIsInternalNote = (isInternalNote: boolean) => setDraft(d => ({ ...d, isInternalNote }))
  const setSending = (sending: boolean) => setDraft(d => ({ ...d, sending }))
  const sendingRef = useRef(false)
  const uploadingRef = useRef(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [previewAttachment, setPreviewAttachment] = useState<import('../../types/support').SupportAttachment | null>(null)
  const [editingMessageUuid, setEditingMessageUuid] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [editingSubject, setEditingSubject] = useState(false)
  const [subjectDraft, setSubjectDraft] = useState('')
  const [savingSubject, setSavingSubject] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const messageRef = useRef<HTMLTextAreaElement>(null)

  // Auto-grow the reply textarea to fit its content (up to a max height).
  useEffect(() => {
    const el = messageRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [message])

  // Error toasts persist until dismissed, so the 15s refresh stays silent on
  // failure — only the initial load reports.
  const loadTicket = useCallback(async () => {
    try {
      const data = await supportApi.getTicket(ticketUuid)
      setTicket(data)
      setLoadError(null)
    } catch {
      setLoadError('Could not refresh this ticket. Your draft is kept.')
    } finally {
      setLoading(false)
    }
  }, [ticketUuid])

  useEffect(() => {
    loadTicket()
    // Mark ticket as read (clears blue dot) and clear notification bell
    supportApi.markTicketRead(ticketUuid).catch(() => {})
    import('../../api/notifications').then(({ markReadForItem }) => {
      markReadForItem('support_ticket', ticketUuid).catch(() => {})
    }).catch(() => {})
    const interval = setInterval(() => loadTicket(), 15000)
    return () => clearInterval(interval)
  }, [loadTicket, ticketUuid])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [ticket?.messages.length])

  const handleSend = async () => {
    if (!message.trim() || sending || sendingRef.current) return
    sendingRef.current = true
    setSending(true)
    try {
      const updated = await supportApi.addMessage(ticketUuid, message.trim(), {
        isInternalNote,
      })
      setTicket(updated)
      setDraft(d => ({ ...d, message: '', isInternalNote: false }))
      onTicketUpdated()
    } catch {
      toast('Failed to send message', 'error')
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const uploadFiles = useCallback(async (picked: File[]) => {
    if (picked.length === 0) return
    if (uploading || uploadingRef.current) {
      setDraft(d => ({ ...d, failedFiles: [...new Set([...d.failedFiles, ...picked])] }))
      return
    }
    const accepted: File[] = []
    for (const f of picked) {
      const sizeMB = (f.size / (1024 * 1024)).toFixed(1)
      if (f.size > MAX_ATTACHMENT_BYTES) {
        toast(`${f.name} is ${sizeMB}MB. Must be under 10MB.`, 'error')
        continue
      }
      accepted.push(f)
    }
    if (accepted.length === 0) return
    uploadingRef.current = true
    setDraft(d => ({ ...d, uploading: true }))
    toast(
      accepted.length === 1
        ? `Uploading ${accepted[0].name}...`
        : `Uploading ${accepted.length} files...`,
      'info',
    )
    try {
      const updated = await supportApi.addAttachment(ticketUuid, accepted)
      setTicket(updated)
      setDraft(d => ({ ...d, failedFiles: d.failedFiles.filter(f => !accepted.includes(f)) }))
      toast(
        accepted.length === 1 ? 'File attached' : `${accepted.length} files attached`,
        'success',
      )
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setDraft(d => ({ ...d, failedFiles: [...new Set([...d.failedFiles, ...accepted])] }))
      toast(`Failed to upload file: ${msg}`, 'error')
    } finally {
      uploadingRef.current = false
      setDraft(d => ({ ...d, uploading: false }))
    }
  }, [ticketUuid, toast, uploading, setDraft])

  const { dragOver, dropRef } = useFileDropZone(uploadFiles)

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? [])
    if (fileInputRef.current) fileInputRef.current.value = ''
    uploadFiles(picked)
  }

  const handleDeleteAttachment = async (attachmentUuid: string, filename: string) => {
    if (!(await confirm({
      title: 'Remove attachment?',
      message: (
        <>
          Remove "{filename}" from this ticket?
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    }))) return
    try {
      const updated = await supportApi.deleteAttachment(ticketUuid, attachmentUuid)
      setTicket(updated)
      toast('Attachment removed', 'success')
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to remove attachment', 'error')
    }
  }

  const handleDeleteMessage = async (messageUuid: string) => {
    if (!(await confirm({
      title: 'Delete this comment?',
      message: "This can't be undone.",
      confirmLabel: 'Delete',
      destructive: true,
    }))) return
    try {
      const updated = await supportApi.deleteMessage(ticketUuid, messageUuid)
      setTicket(updated)
      toast('Message deleted', 'success')
      onTicketUpdated()
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to delete message', 'error')
    }
  }

  const startEdit = (msg: import('../../types/support').SupportMessage) => {
    setEditingMessageUuid(msg.uuid)
    setEditDraft(msg.content)
  }

  const cancelEdit = () => {
    setEditingMessageUuid(null)
    setEditDraft('')
  }

  const saveEdit = async () => {
    if (!editingMessageUuid) return
    const trimmed = editDraft.trim()
    if (!trimmed) return
    setSavingEdit(true)
    try {
      const updated = await supportApi.editMessage(ticketUuid, editingMessageUuid, trimmed)
      setTicket(updated)
      cancelEdit()
    } catch (err) {
      const m = err instanceof Error ? err.message : 'Could not save edit'
      toast(m, 'error')
    } finally {
      setSavingEdit(false)
    }
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

  const startEditSubject = () => {
    if (!ticket) return
    setSubjectDraft(ticket.subject)
    setEditingSubject(true)
  }

  const saveSubject = async () => {
    if (!ticket) return
    const trimmed = subjectDraft.trim()
    if (!trimmed || trimmed === ticket.subject) {
      setEditingSubject(false)
      return
    }
    setSavingSubject(true)
    try {
      const updated = await supportApi.updateTicket(ticketUuid, { subject: trimmed })
      setTicket(updated)
      setEditingSubject(false)
      onTicketUpdated()
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to update subject', 'error')
    } finally {
      setSavingSubject(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-gray-600" />
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-gray-500">
        <p role="alert" className="text-sm">{loadError || 'Ticket not found'}</p>
        {loadError && <button type="button" onClick={() => { setLoading(true); void loadTicket() }} className="text-xs text-blue-700 underline">Retry ticket</button>}
        <button onClick={onBack} className="text-xs text-blue-600 hover:underline">Back</button>
      </div>
    )
  }

  const StatusIcon = ticket.status === 'closed' ? CheckCircle2 : ticket.status === 'in_progress' ? Clock : Circle

  return (
    <div ref={dropRef} className="relative flex flex-1 flex-col overflow-hidden">
      <DropOverlay show={dragOver} />
      {/* Chat header */}
      <div className="border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <button type="button" onClick={onBack} aria-label="Back" className="rounded p-1 text-gray-600 hover:bg-gray-100 hover:text-gray-600">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            {editingSubject ? (
              <div className="flex items-center gap-1">
                {ticket.ticket_number != null && (
                  <span className="font-mono text-[11px] text-gray-600">#{ticket.ticket_number}</span>
                )}
                <input
                  autoFocus
                  value={subjectDraft}
                  onChange={e => setSubjectDraft(e.target.value)}
                  onBlur={saveSubject}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { e.preventDefault(); saveSubject() }
                    if (e.key === 'Escape') setEditingSubject(false)
                  }}
                  maxLength={200}
                  disabled={savingSubject}
                  aria-label="Edit ticket subject"
                  className="min-w-0 flex-1 rounded border border-gray-300 px-1.5 py-0.5 text-sm font-medium text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-60"
                />
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {ticket.ticket_number != null && (
                    <span className="mr-1 font-mono text-[11px] text-gray-600">#{ticket.ticket_number}</span>
                  )}
                  {ticket.subject}
                </p>
                {(isSupportAgent || ticket.user_id === user?.user_id) && (
                  <button
                    type="button"
                    onClick={startEditSubject}
                    aria-label="Edit subject"
                    title="Edit subject"
                    className="rounded p-0.5 text-gray-300 hover:bg-gray-100 hover:text-gray-500"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
              </div>
            )}
            <div className="flex items-center gap-2">
              <StatusIcon className={`h-3 w-3 ${
                ticket.status === 'closed' ? 'text-gray-600' : ticket.status === 'in_progress' ? 'text-blue-500' : 'text-yellow-500'
              }`} />
              <span className="text-[10px] text-gray-600">
                {ticket.status === 'closed' ? 'Closed' : ticket.status === 'in_progress' ? 'In progress' : 'Open'}
              </span>
              {isSupportAgent && (
                <>
                  <span className="text-[10px] text-gray-500">|</span>
                  <span className={`text-[10px] font-medium ${PRIORITY_COLORS[ticket.priority]}`}>
                    {ticket.priority}
                  </span>
                  {ticket.classification && (
                    <>
                      <span className="text-[10px] text-gray-500">|</span>
                      <span className="text-[10px] font-medium text-indigo-500">
                        {CLASSIFICATION_LABELS[ticket.classification]}
                      </span>
                    </>
                  )}
                  <span className="text-[10px] text-gray-500">|</span>
                  <span className="text-[10px] text-gray-500">{ticket.user_name || ticket.user_id}</span>
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

        {/* Watchers — visible to everyone on the ticket */}
        <WatcherBar
          ticket={ticket}
          currentUserId={user?.user_id ?? ''}
          onChange={setTicket}
        />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {ticket.messages.map((msg) => {
          const isMe = msg.user_id === user?.user_id
          // Author or admin — regular support agents can't delete other
          // people's messages (mirrors the backend gate).
          const canDeleteMsg = !!user && (user.is_admin || msg.user_id === user.user_id)
          const isInternal = msg.is_internal_note
          const isEditing = editingMessageUuid === msg.uuid
          const msgAttachments = ticket.attachments.filter(a => a.message_uuid === msg.uuid)
          // Internal notes span the full row with a yellow card so agents
          // never confuse them with a real reply to the requester.
          const wrapperClass = isInternal
            ? 'group flex flex-col items-stretch'
            : `group flex flex-col ${isMe ? 'items-end' : 'items-start'}`
          const bubbleClass = isInternal
            ? 'w-full rounded-xl border border-yellow-500 border-l-[5px] border-l-yellow-600 bg-yellow-100 px-3 py-2 text-yellow-900'
            : `max-w-[85%] rounded-xl px-3 py-2 ${
                isMe ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900'
              }`
          return (
            <div key={msg.uuid} className={wrapperClass}>
              <div className={bubbleClass}>
                {isInternal && (
                  <div className="mb-1.5 flex items-center justify-between gap-2 border-b border-dashed border-yellow-500 pb-1.5">
                    <span className="inline-flex items-center gap-1 rounded bg-yellow-300 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-yellow-900">
                      <Lock className="h-2.5 w-2.5" />
                      Internal note · Agents only
                    </span>
                    <span className="text-[9px] italic text-yellow-800">
                      Not visible to the requester
                    </span>
                  </div>
                )}
                {!isMe && !isInternal && (
                  <p className="mb-0.5 text-[10px] font-medium text-gray-500">
                    {msg.user_name || 'Support'}
                  </p>
                )}
                {isInternal && (
                  <p className="mb-0.5 text-[10px] font-medium text-yellow-800">
                    {msg.user_name || msg.user_id}
                  </p>
                )}
                {isEditing ? (
                  <div className="flex flex-col gap-1.5">
                    <textarea
                      autoFocus
                      aria-label="Edit message"
                      value={editDraft}
                      onChange={(e) => setEditDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault()
                          saveEdit()
                        }
                        if (e.key === 'Escape') {
                          e.preventDefault()
                          cancelEdit()
                        }
                      }}
                      rows={Math.min(8, Math.max(2, editDraft.split('\n').length))}
                      className={
                        isInternal
                          ? 'resize-none rounded-md px-2 py-1 text-sm text-gray-900 bg-white border border-yellow-400 focus:outline-none focus:ring-2 focus:ring-yellow-400'
                          : 'resize-none rounded-md px-2 py-1 text-sm text-gray-900 bg-white/95 focus:outline-none focus:ring-2 focus:ring-blue-300'
                      }
                    />
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={cancelEdit}
                        disabled={savingEdit}
                        className={
                          isInternal
                            ? 'rounded px-2 py-0.5 text-[11px] font-medium text-yellow-900 hover:bg-yellow-200 disabled:opacity-50'
                            : 'rounded px-2 py-0.5 text-[11px] font-medium text-white hover:bg-blue-700 disabled:opacity-50'
                        }
                      >
                        Cancel
                      </button>
                      <button
                        onClick={saveEdit}
                        disabled={savingEdit || !editDraft.trim()}
                        className={
                          isInternal
                            ? 'inline-flex items-center gap-1 rounded bg-yellow-800 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-yellow-900 disabled:opacity-50'
                            : 'inline-flex items-center gap-1 rounded bg-blue-800 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-blue-900 disabled:opacity-50'
                        }
                      >
                        {savingEdit ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                        Save
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                )}
                <p className={`mt-1 text-[10px] ${isInternal ? 'text-yellow-800' : (isMe ? 'text-white' : 'text-gray-600')}`}>
                  {timeAgo(msg.created_at)}
                  {msg.edited_at && <span className="ml-1 italic">(edited)</span>}
                </p>
              </div>
              {(isMe || canDeleteMsg) && !isEditing && (
                <div className="mt-0.5 flex items-center gap-0.5">
                  {isMe && (
                    <button
                      onClick={() => startEdit(msg)}
                      className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] text-gray-600 hover:bg-gray-100 hover:text-gray-800"
                      title="Edit message"
                    >
                      <Pencil className="h-2.5 w-2.5" />
                      Edit
                    </button>
                  )}
                  {canDeleteMsg && (
                    <button
                      onClick={() => handleDeleteMessage(msg.uuid)}
                      className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] text-gray-600 hover:bg-red-50 hover:text-red-700"
                      title="Delete message"
                    >
                      <Trash2 className="h-2.5 w-2.5" />
                      Delete
                    </button>
                  )}
                </div>
              )}
              {msgAttachments.length > 0 && (
                <div className={`flex flex-col gap-1.5 mt-1.5 max-w-[85%] ${isMe ? 'items-end' : 'items-start'}`}>
                  {msgAttachments.map((a) => {
                    const canDelete = !!user && (isSupportAgent || a.uploaded_by === user.user_id)
                    return (
                      <AttachmentChip
                        key={a.uuid}
                        attachment={a}
                        ticketUuid={ticketUuid}
                        onPreview={setPreviewAttachment}
                        onDelete={canDelete ? () => handleDeleteAttachment(a.uuid, a.filename) : undefined}
                      />
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
              const canDelete = !!user && (isSupportAgent || a.uploaded_by === user.user_id)
              return (
                <AttachmentChip
                  key={a.uuid}
                  attachment={a}
                  ticketUuid={ticketUuid}
                  onPreview={setPreviewAttachment}
                  onDelete={canDelete ? () => handleDeleteAttachment(a.uuid, a.filename) : undefined}
                />
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

      {/* Dismiss option for unanswered feedback prompt tickets */}
      {onDismissPrompt && ticket.category === 'feedback_prompt' && ticket.messages.length <= 1 && (
        <div className="border-t px-3 py-1.5 text-center">
          <button
            onClick={() => {
              onDismissPrompt()
              onBack()
            }}
            className="text-xs text-gray-600 hover:text-gray-600 transition-colors"
          >
            Not now
          </button>
        </div>
      )}

      {/* Input */}
      {loadError && <div role="alert" className="px-3 py-2 text-xs text-red-800">{loadError} <button type="button" className="underline" onClick={() => void loadTicket()}>Retry ticket</button></div>}
      {uploading && <p role="status" className="px-3 text-xs text-gray-700">Uploading attachments…</p>}
      {failedFiles.length > 0 && <div role="alert" className="px-3 py-2 text-xs text-red-800">Not uploaded: {failedFiles.map(f => f.name).join(', ')}. <button type="button" disabled={uploading} className="underline" onClick={() => void uploadFiles(failedFiles)}>Retry attachments</button></div>}
      <div className={`border-t px-3 py-2 ${isInternalNote ? 'bg-yellow-100' : ''}`}>
        {isSupportAgent && (
          <div className="mb-1.5 flex items-center justify-between">
            <button
              type="button"
              disabled={sending}
              onClick={() => setIsInternalNote(!isInternalNote)}
              title={isInternalNote
                ? 'Only other support agents will see this'
                : 'Switch to an internal note, visible only to support agents'}
              className={
                isInternalNote
                  ? 'inline-flex items-center gap-1 rounded-full border border-yellow-500 bg-yellow-200 px-2 py-0.5 text-[10px] font-semibold text-yellow-900'
                  : 'inline-flex items-center gap-1 rounded-full border border-gray-300 px-2 py-0.5 text-[10px] font-semibold text-gray-500 hover:border-yellow-400 hover:text-yellow-700'
              }
            >
              <Lock className="h-2.5 w-2.5" />
              {isInternalNote ? 'Internal note' : 'Add internal note'}
            </button>
            {isInternalNote && (
              <span className="text-[10px] italic text-yellow-800">Hidden from requester</span>
            )}
          </div>
        )}
        <div className="flex items-end gap-1.5">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="rounded p-1.5 text-gray-600 hover:bg-gray-100 hover:text-gray-600"
            title="Attach file"
            aria-label="Attach file"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input ref={fileInputRef} type="file" multiple aria-label="Upload files" className="hidden" onChange={handleFileUpload} />
          <textarea
            ref={messageRef}
            aria-label="Message"
            disabled={sending}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              ticket.status === 'closed'
                ? 'Reply to reopen...'
                : isInternalNote
                  ? 'Leave a note for other agents...'
                  : 'Type a message...'
            }
            rows={1}
            className={`max-h-40 flex-1 resize-none overflow-y-auto rounded-lg px-3 py-1.5 text-sm focus:outline-none ${
              isInternalNote
                ? 'border border-yellow-400 bg-white focus:border-yellow-500'
                : 'border border-gray-300 focus:border-blue-500'
            }`}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!message.trim() || sending}
            aria-label={isInternalNote ? 'Add internal note' : 'Send message'}
            className={`rounded-lg p-1.5 text-white disabled:opacity-50 ${
              isInternalNote ? 'bg-yellow-800 hover:bg-yellow-900' : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {sending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isInternalNote ? (
              <Lock className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Watcher bar — tagged users who see and follow the ticket
// ---------------------------------------------------------------------------

function WatcherBar({
  ticket,
  currentUserId,
  onChange,
}: {
  ticket: SupportTicket
  currentUserId: string
  onChange: (next: SupportTicket) => void
}) {
  const { toast } = useToast()
  const [adding, setAdding] = useState(false)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)

  const watchers = ticket.watchers ?? []
  // Anyone who can view the ticket can add/remove watchers from the UI; the
  // backend enforces the actual rule (owner, support, or self-remove). We
  // simplify the client by always showing controls and letting a 403 toast.

  const submit = async () => {
    const trimmed = email.trim()
    if (!trimmed || busy) return
    setBusy(true)
    try {
      const updated = await supportApi.addWatcher(ticket.uuid, trimmed)
      onChange(updated)
      setEmail('')
      setAdding(false)
      toast('Watcher added', 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not add watcher'
      toast(msg, 'error')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (userId: string) => {
    try {
      const updated = await supportApi.removeWatcher(ticket.uuid, userId)
      onChange(updated)
    } catch {
      toast('Could not remove watcher', 'error')
    }
  }

  return (
    <div className="mt-2 ml-7 flex flex-wrap items-center gap-1.5">
      <span
        className="inline-flex items-center gap-1 text-[10px] font-medium uppercase text-gray-500"
        title="Tagged users follow this ticket and get notified on updates"
      >
        <Eye className="h-3 w-3" />
        Watchers
      </span>
      {watchers.length === 0 && !adding && (
        <span className="text-[11px] text-gray-500">None</span>
      )}
      {watchers.map((w) => {
        const isMe = w.user_id === currentUserId
        return (
          <span
            key={w.user_id}
            className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700"
            title={w.email || w.user_id}
          >
            {isMe ? 'You' : w.name}
            <button
              onClick={() => remove(w.user_id)}
              className="rounded-full p-0.5 text-indigo-500 hover:bg-indigo-100 hover:text-indigo-900"
              title={isMe ? 'Stop watching' : `Remove ${w.name}`}
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </span>
        )
      })}
      {adding ? (
        <input
          autoFocus
          aria-label="Watcher email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => { if (!busy) { setEmail(''); setAdding(false) } }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); submit() }
            if (e.key === 'Escape') { setEmail(''); setAdding(false) }
          }}
          placeholder="email…"
          type="email"
          disabled={busy}
          className="rounded-full border border-gray-300 px-2 py-0.5 text-[11px] outline-none focus:border-blue-500 disabled:opacity-50"
          style={{ minWidth: 140 }}
        />
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-2 py-0.5 text-[11px] text-gray-500 hover:border-blue-400 hover:text-blue-600"
          title="Tag a user to follow this ticket"
        >
          <UserPlus className="h-2.5 w-2.5" />
          Tag user
        </button>
      )}
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
  onDismissPrompt,
}: {
  open: boolean
  onClose: () => void
  initialTicket?: string
  onDismissPrompt?: () => void
}) {
  const { user } = useAuth()
  const isSupportAgent = user?.is_support_agent ?? false

  const [view, setView] = useState<View>(initialTicket ? 'chat' : 'list')
  const [draft, setDraft] = useState<TicketDraft>(emptyTicketDraft)
  const [replyDrafts, setReplyDrafts] = useState<Record<string, ReplyDraft>>({})
  const [ticketSubmitting, setTicketSubmitting] = useState(false)
  const [pendingContext, setPendingContext] = useState<SupportDraftContext | null>(null)
  const addedContexts = useRef(new Set<string>())
  const [activeTicket, setActiveTicket] = useState<string | null>(initialTicket || null)
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [ticketsError, setTicketsError] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const currentUserId = user?.user_id ?? ''

  const loadTickets = useCallback(async () => {
    try {
      const data = await supportApi.listTickets(undefined, 50)
      setTickets(data.tickets)
      setTicketsError(null)
    } catch {
      setTicketsError('Could not refresh your tickets.')
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

  // Sync with the ticket the parent asked to open. Used by the feedback
  // prompt and Support button flows that drive `initialTicket` via state.
  useEffect(() => {
    if (!open) return
    if (initialTicket) {
      setActiveTicket(initialTicket)
      setView('chat')
    }
  }, [open, initialTicket])

  // Also listen for `open-support-panel` events directly. The parent only
  // sees a state change when the event's ticket uuid differs from what it
  // was last asked to open — so re-clicking the same notification after the
  // user has navigated back to the list would otherwise be a no-op. Reading
  // the event ourselves lets every click jump back to the ticket.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      const ticketUuid = detail?.ticketUuid
      if (ticketUuid) {
        setActiveTicket(ticketUuid)
        setView('chat')
      } else if (detail?.draft) {
        setPendingContext(detail.draft)
      }
    }
    window.addEventListener('open-support-panel', handler)
    return () => window.removeEventListener('open-support-panel', handler)
  }, [])

  // Keep an outgoing ticket's draft untouched until its request settles. New
  // context is then added to the remaining draft, preserving text and files.
  useEffect(() => {
    if (!pendingContext || ticketSubmitting) return
    if (!addedContexts.current.has(pendingContext.key)) {
      addedContexts.current.add(pendingContext.key)
      setDraft(current => ({
        ...current,
        subject: current.subject.trim() ? current.subject : pendingContext.subject,
        message: current.message.trim() ? `${current.message}\n\n${pendingContext.message}` : pendingContext.message,
      }))
    }
    setView('new')
    setPendingContext(null)
  }, [pendingContext, ticketSubmitting])

  // This panel is nonmodal: users may still read the workspace. Return focus
  // only when closing from inside it, without stealing focus from other work.
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const panel = panelRef.current
    panel?.focus({ preventScroll: true })
    return () => {
      if (panel?.contains(document.activeElement) || document.activeElement === document.body) {
        previous?.focus({ preventScroll: true })
      }
    }
  }, [open])

  if (!open) return null

  // Count tickets needing attention for the title bar badge
  const attentionCount = tickets.filter(t => {
    if (t.status === 'closed' || !t.last_message_user_id) return false
    const isNew = isSupportAgent
      ? t.last_message_is_support_reply === false
      : t.last_message_is_support_reply === true
    if (!isNew) return false
    if (t.read_by?.includes(currentUserId)) return false
    return true
  }).length

  return createPortal(
    <div
      ref={panelRef}
      role="region" aria-label="Support" tabIndex={-1}
      onKeyDown={e => { if (e.key === 'Escape' && !e.defaultPrevented) { e.stopPropagation(); onClose() } }}
      className="fixed bottom-4 right-4 z-[9998] flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
      style={{ width: 'min(380px, calc(100vw - 32px))', height: 'min(520px, calc(100dvh - 32px))' }}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between bg-panel-dark px-4 py-3 text-white">
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
        <button type="button" aria-label="Close support" onClick={onClose} className="rounded p-2 hover:bg-white/10">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Content area */}
      {view === 'list' && ticketsError && <div role="alert" className="p-3 text-sm text-red-800">{ticketsError} {tickets.length > 0 ? 'Showing the last loaded list.' : ''} <button type="button" className="underline" onClick={() => void loadTickets()}>Retry tickets</button></div>}
      {view === 'list' && (!ticketsError || tickets.length > 0) && (
        <TicketListView
          tickets={tickets}
          loading={loading}
          isSupportAgent={isSupportAgent}
          currentUserId={currentUserId}
          onSelect={(uuid) => {
            setActiveTicket(uuid)
            setView('chat')
          }}
          onNew={() => setView('new')}
          onPraise={() => setView('praise')}
        />
      )}

      {view === 'praise' && (
        <PraiseView onBack={() => setView('list')} />
      )}

      {view === 'new' && (
        <NewTicketView
          submitting={ticketSubmitting}
          setSubmitting={setTicketSubmitting}
          draft={draft}
          setDraft={setDraft}
          onBack={() => setView('list')}
          onCreated={(ticket) => {
            setDraft(emptyTicketDraft())
            addedContexts.current.clear()
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
          draft={replyDrafts[activeTicket] ?? emptyReplyDraft()}
          setDraft={update => setReplyDrafts(all => ({ ...all, [activeTicket]: typeof update === 'function' ? update(all[activeTicket] ?? emptyReplyDraft()) : update }))}
          isSupportAgent={isSupportAgent}
          onBack={() => {
            setView('list')
            setActiveTicket(null)
            loadTickets()
          }}
          onTicketUpdated={loadTickets}
          onDismissPrompt={onDismissPrompt}
        />
      )}
    </div>,
    document.body,
  )
}
