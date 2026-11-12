/** Server event timestamps are UTC, including older responses without an offset.
 * Date-only inputs remain dates; explicit Z/offsets keep their original instant. */
export function parseServerTimestamp(value: string): Date {
  const timestamp = value.trim()
  const naive = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(timestamp)
  return new Date(naive ? `${timestamp.replace(' ', 'T')}Z` : timestamp)
}

/** Full local time, with the browser's zone identified for run details. */
export function formatLocalTimestamp(value: string | null | undefined): string {
  const date = value ? parseServerTimestamp(value) : null
  return date && Number.isFinite(date.getTime())
    ? date.toLocaleString(undefined, { timeZoneName: 'short' })
    : 'Time unavailable'
}

/**
 * Convert an ISO date string to a human-readable relative time string.
 */
export function relativeTime(dateStr: string): string {
  const diff = Date.now() - parseServerTimestamp(dateStr).getTime()
  if (!Number.isFinite(diff)) return 'Time unavailable'
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * File-friendly date formatter.
 * Recent: "Just now", "5m ago", "3h ago", "2d ago"
 * Older: "Mar 5" (same year) or "Mar 5, 2025" (different year)
 */
export function formatFileDate(dateStr: string): string {
  const date = parseServerTimestamp(dateStr)
  if (!Number.isFinite(date.getTime())) return 'Time unavailable'
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days <= 6) return `${days}d ago`
  const month = SHORT_MONTHS[date.getMonth()]
  const day = date.getDate()
  if (date.getFullYear() === now.getFullYear()) return `${month} ${day}`
  return `${month} ${day}, ${date.getFullYear()}`
}
