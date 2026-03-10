/**
 * Convert an ISO date string to a human-readable relative time string.
 */
export function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
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
  const date = new Date(dateStr)
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
