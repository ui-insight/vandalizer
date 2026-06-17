/**
 * Status indicator dot. Accepts any string; maps common optimization-run
 * statuses to canonical colors and falls back to neutral for unknown values.
 */
const STATUS_COLORS: Record<string, string> = {
  completed: '#22c55e',
  cancelled: '#888',
  failed: '#ef4444',
  queued: '#a78bfa',
  running: '#a78bfa',
}

interface StatusDotProps {
  status: string
  size?: number
}

export function StatusDot({ status, size = 7 }: StatusDotProps) {
  const color = STATUS_COLORS[status] ?? '#888'
  return (
    <span style={{ width: size, height: size, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
  )
}
