import { CheckCircle2, CirclePause, Clock3, CircleHelp, CircleAlert } from 'lucide-react'

/** A recorded execution state, separate from availability and measured quality. */
export function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase()
  const success = ['completed', 'succeeded', 'ready', 'enabled'].includes(key)
  const failed = ['failed', 'error'].includes(key)
  const active = ['queued', 'running', 'processing'].includes(key)
  const paused = ['paused', 'cancelled', 'canceled', 'disabled'].includes(key)
  const Icon = success ? CheckCircle2 : failed ? CircleAlert : active ? Clock3 : paused ? CirclePause : CircleHelp
  return <span className="workspace-status-badge" data-tone={success ? 'success' : failed ? 'danger' : active ? 'info' : 'neutral'}><Icon size={14} aria-hidden="true" />{status ? status.charAt(0).toUpperCase() + status.slice(1).replaceAll('_', ' ') : 'Unknown'}</span>
}
