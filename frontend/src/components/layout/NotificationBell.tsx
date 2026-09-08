import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bell, CheckCheck, FileX, Headphones, Inbox, MessageSquare, ShieldCheck, ShieldX, RotateCcw, Eye, Share2, Timer, TrendingDown, XOctagon } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { listNotifications, markRead, markAllRead, getUnreadCount } from '../../api/notifications'
import type { Notification } from '../../api/notifications'
import { relativeTime } from '../../utils/time'
import { openSupportPanel } from '../../utils/supportPanel'

const FAILURE_RED = '#dc2626'

const kindIcons: Record<string, typeof ShieldCheck> = {
  verification_submitted: Inbox,
  verification_approved: ShieldCheck,
  verification_rejected: ShieldX,
  verification_returned: RotateCcw,
  verification_in_review: Eye,
  support_new_ticket: Headphones,
  support_new_message: MessageSquare,
  support_reply: MessageSquare,
  support_status: Headphones,
  team_share: Share2,
  workflow_failed: XOctagon,
  extraction_failed: AlertTriangle,
  document_failed: FileX,
  automation_failed: Timer,
  quality_regression: TrendingDown,
}

const kindColors: Record<string, string> = {
  verification_submitted: '#f1b300',
  verification_approved: '#15803d',
  verification_rejected: '#dc2626',
  verification_returned: '#d97706',
  verification_in_review: '#2563eb',
  support_new_ticket: '#7c3aed',
  support_new_message: '#7c3aed',
  support_reply: '#2563eb',
  support_status: '#059669',
  team_share: '#f1b300',
  workflow_failed: FAILURE_RED,
  extraction_failed: FAILURE_RED,
  document_failed: FAILURE_RED,
  automation_failed: FAILURE_RED,
  // Not in FAILURE_KINDS, so a warning-severity regression (the ones that get
  // no email by design) would otherwise fall through to a generic grey bell —
  // indistinguishable from an informational notice.
  quality_regression: '#d97706',
}

const SUPPORT_KINDS = new Set([
  'support_new_ticket',
  'support_new_message',
  'support_reply',
  'support_status',
])

function extractTicketUuid(link: string | null): string | undefined {
  if (!link) return undefined
  const match = link.match(/ticket=([a-f0-9]+)/)
  return match?.[1]
}

/**
 * Split a stored link into the pathname and search object the router expects.
 *
 * Failure notifications deep-link into the workspace via query params
 * (`/?workflow=<id>`, `/?mode=automations&automation=<id>`), and passing the
 * whole string as `to` leaves the params on the floor.
 */
export function parseNotificationLink(link: string): {
  to: string
  search: Record<string, string>
} {
  const [path, query] = link.split('?')
  const search: Record<string, string> = {}
  if (query) {
    for (const [key, value] of new URLSearchParams(query)) search[key] = value
  }
  return { to: path || '/', search }
}

export function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const ref = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await listNotifications(false, 20)
      setNotifications(data.notifications)
      setUnreadCount(data.unread_count)
    } catch {
      // silent
    }
  }, [])

  // Poll for unread count every 30s
  useEffect(() => {
    refresh()
    const interval = setInterval(async () => {
      try {
        const data = await getUnreadCount()
        setUnreadCount(data.unread_count)
      } catch {
        // silent
      }
    }, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleToggle = () => {
    if (!open) refresh()
    setOpen(!open)
  }

  const handleMarkRead = async (n: Notification) => {
    if (!n.read) {
      await markRead(n.uuid)
      setNotifications(prev => prev.map(x => x.uuid === n.uuid ? { ...x, read: true } : x))
      setUnreadCount(prev => Math.max(0, prev - 1))
    }

    // Support notifications open the chat panel instead of navigating
    if (SUPPORT_KINDS.has(n.kind)) {
      const ticketUuid = n.item_id || extractTicketUuid(n.link)
      openSupportPanel(ticketUuid)
      setOpen(false)
      return
    }

    if (n.link) {
      const { to, search } = parseNotificationLink(n.link)
      navigate({ to, search })
      setOpen(false)
    }
  }

  const handleMarkAllRead = async () => {
    await markAllRead()
    setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    setUnreadCount(0)
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={handleToggle}
        className="relative flex items-center justify-center rounded-full border border-gray-300 p-1.5 text-gray-500 hover:bg-gray-100 transition-all"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex items-center justify-center h-4 min-w-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 z-[9000] w-80 bg-white border border-gray-200 rounded-lg shadow-xl">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
              >
                <CheckCheck className="h-3 w-3" />
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-500">
                No notifications yet
              </div>
            ) : (
              notifications.map(n => {
                const isFailure = n.severity === 'error'
                const Icon = kindIcons[n.kind] || (isFailure ? AlertTriangle : Bell)
                const color = kindColors[n.kind] || (isFailure ? FAILURE_RED : '#6b7280')
                return (
                  <button
                    key={n.uuid}
                    onClick={() => handleMarkRead(n)}
                    className={`w-full text-left flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-50 ${
                      n.read ? 'opacity-60' : ''
                    } ${isFailure && !n.read ? 'bg-red-50/60' : ''}`}
                  >
                    <Icon className="h-4 w-4 shrink-0 mt-0.5" style={{ color }} />
                    <div className="min-w-0 flex-1">
                      <p className={`text-sm ${n.read ? 'text-gray-600' : 'text-gray-900 font-medium'}`}>
                        {n.title}
                      </p>
                      {n.body && (
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.body}</p>
                      )}
                      <p className="text-xs text-gray-500 mt-1">
                        {n.created_at && relativeTime(n.created_at)}
                        {n.occurrences > 1 && (
                          <span className="ml-1 text-gray-400">
                            {n.created_at && '· '}
                            {`${n.occurrences} occurrences`}
                          </span>
                        )}
                      </p>
                    </div>
                    {!n.read && (
                      <span
                        className="h-2 w-2 rounded-full shrink-0 mt-1.5"
                        style={{ backgroundColor: isFailure ? FAILURE_RED : '#3b82f6' }}
                      />
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
