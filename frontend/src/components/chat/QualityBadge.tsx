import { useState, useRef, useEffect } from 'react'
import { Shield, ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react'
import type { QualityMeta } from '../../types/chat'

const TIER_CONFIG: Record<string, { bg: string; border: string; text: string; icon: typeof Shield; label: string }> = {
  excellent: { bg: 'rgba(34,197,94,0.10)', border: '#22c55e', text: '#15803d', icon: ShieldCheck, label: 'Verified' },
  good:      { bg: 'rgba(234,179,8,0.10)', border: '#eab308', text: '#a16207', icon: ShieldCheck, label: 'Good' },
  fair:      { bg: 'rgba(148,163,184,0.10)', border: '#94a3b8', text: '#475569', icon: Shield, label: 'Fair' },
  poor:      { bg: 'rgba(239,68,68,0.08)', border: '#ef4444', text: '#dc2626', icon: ShieldAlert, label: 'Low' },
}

const DEFAULT_CONFIG = { bg: 'rgba(148,163,184,0.06)', border: '#cbd5e1', text: '#64748b', icon: Shield, label: 'Unscored' }

function formatDate(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = new Date()
  const days = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days} days ago`
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`
  return d.toLocaleDateString()
}

export function QualityBadge({ quality }: { quality: QualityMeta }) {
  if (quality.score == null && !quality.tier) return null

  const [showTooltip, setShowTooltip] = useState(false)
  const badgeRef = useRef<HTMLButtonElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const tier = quality.tier?.toLowerCase() ?? ''
  const config = TIER_CONFIG[tier] || DEFAULT_CONFIG
  const IconComponent = config.icon
  const hasAlerts = (quality.active_alerts?.length ?? 0) > 0

  // Close tooltip on outside click
  useEffect(() => {
    if (!showTooltip) return
    const handler = (e: MouseEvent) => {
      if (
        badgeRef.current && !badgeRef.current.contains(e.target as Node) &&
        tooltipRef.current && !tooltipRef.current.contains(e.target as Node)
      ) {
        setShowTooltip(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showTooltip])

  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        ref={badgeRef}
        onClick={(e) => { e.stopPropagation(); setShowTooltip(!showTooltip) }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '2px 8px',
          borderRadius: 9999,
          fontSize: 11,
          fontWeight: 500,
          lineHeight: '18px',
          background: config.bg,
          border: `1px solid ${config.border}`,
          color: config.text,
          cursor: 'pointer',
          position: 'relative',
          fontFamily: 'inherit',
        }}
      >
        <IconComponent size={12} />
        {quality.score != null && (
          <span style={{ fontWeight: 600 }}>{Math.round(quality.score)}</span>
        )}
        <span>{config.label}</span>
        {hasAlerts && (
          <AlertTriangle size={10} style={{ color: '#f59e0b', marginLeft: -2 }} />
        )}
      </button>

      {/* Rich tooltip */}
      {showTooltip && (
        <div
          ref={tooltipRef}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            bottom: '100%',
            right: 0,
            marginBottom: 6,
            width: 240,
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 12,
            zIndex: 100,
            fontSize: 12,
            color: '#374151',
            lineHeight: 1.5,
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid #f3f4f6' }}>
            <IconComponent size={16} style={{ color: config.text }} />
            <span style={{ fontWeight: 600, fontSize: 13 }}>
              {quality.score != null ? `Quality Score: ${Math.round(quality.score)}/100` : 'No Score'}
            </span>
          </div>

          {/* Metrics */}
          {(quality.accuracy != null || quality.consistency != null) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginBottom: 8 }}>
              {quality.accuracy != null && (
                <>
                  <span style={{ color: '#6b7280' }}>Accuracy</span>
                  <span style={{ fontWeight: 500, textAlign: 'right' }}>{Math.round(quality.accuracy * 100)}%</span>
                </>
              )}
              {quality.consistency != null && (
                <>
                  <span style={{ color: '#6b7280' }}>Consistency</span>
                  <span style={{ fontWeight: 500, textAlign: 'right' }}>{Math.round(quality.consistency * 100)}%</span>
                </>
              )}
              {quality.num_test_cases != null && (
                <>
                  <span style={{ color: '#6b7280' }}>Test cases</span>
                  <span style={{ fontWeight: 500, textAlign: 'right' }}>{quality.num_test_cases}</span>
                </>
              )}
              {quality.num_runs != null && (
                <>
                  <span style={{ color: '#6b7280' }}>Validation runs</span>
                  <span style={{ fontWeight: 500, textAlign: 'right' }}>{quality.num_runs}</span>
                </>
              )}
            </div>
          )}

          {/* Last validated */}
          <div style={{ color: '#9ca3af', fontSize: 11 }}>
            Last validated: {formatDate(quality.last_validated_at)}
          </div>

          {/* Alerts */}
          {hasAlerts && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
              {quality.active_alerts!.map((alert, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 6,
                    padding: '4px 0',
                    fontSize: 11,
                    color: alert.severity === 'critical' ? '#dc2626' : '#d97706',
                  }}
                >
                  <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span>{alert.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  )
}
