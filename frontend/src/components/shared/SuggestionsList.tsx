import { AlertCircle, AlertTriangle, Info } from 'lucide-react'
import type { ReactNode } from 'react'

export type SuggestionSeverity = 'critical' | 'warning' | 'info'

export interface Suggestion {
  severity: SuggestionSeverity
  message: string
  /** Optional inline action (e.g. "Apply this fix"). When set, renders as a button. */
  onAction?: () => void
  actionLabel?: string
}

const DEFAULT_ICONS: Record<SuggestionSeverity, ReactNode> = {
  critical: <AlertCircle size={13} />,
  warning: <AlertTriangle size={13} />,
  info: <Info size={13} />,
}

const COLORS: Record<SuggestionSeverity, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#3b82f6',
}

interface SuggestionsListProps {
  suggestions: Suggestion[]
  title?: string
  /** Override per-severity icon. Falls back to AlertCircle / AlertTriangle / Info. */
  icons?: Partial<Record<SuggestionSeverity, ReactNode>>
  /** Hide the wrapping card chrome — render rows only. */
  bare?: boolean
}

export function SuggestionsList({
  suggestions, title = 'Suggestions', icons, bare = false,
}: SuggestionsListProps) {
  if (suggestions.length === 0) return null

  const rows = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {suggestions.map((s, i) => {
        const icon = icons?.[s.severity] ?? DEFAULT_ICONS[s.severity]
        const color = COLORS[s.severity]
        return (
          <div
            key={i}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 8,
              padding: '8px 10px',
              backgroundColor: `${color}0e`,
              border: `1px solid ${color}33`,
              borderRadius: 6,
            }}
          >
            <span style={{ color, flexShrink: 0, marginTop: 2, display: 'flex' }}>
              {icon}
            </span>
            <div style={{ flex: 1, fontSize: 12, color: '#ddd', lineHeight: 1.5 }}>
              {s.message}
            </div>
            {s.onAction && s.actionLabel && (
              <button
                onClick={s.onAction}
                style={{
                  padding: '3px 8px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
                  color, background: 'transparent',
                  border: `1px solid ${color}66`, borderRadius: 4,
                  cursor: 'pointer', flexShrink: 0,
                }}
              >
                {s.actionLabel}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )

  if (bare) return rows

  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', marginBottom: 10 }}>
        {title}
      </div>
      {rows}
    </div>
  )
}
