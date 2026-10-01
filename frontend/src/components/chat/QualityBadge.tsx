import { useState, useRef, useId } from 'react'
import { usePanelEffect } from '../shared/usePanelEffect'
import { createPortal } from '../shared/panelPortal'
import { Shield, ShieldAlert, ShieldCheck, AlertTriangle, Sparkles } from 'lucide-react'
import type { QualityMeta } from '../../types/chat'

// Labels and colors match QUALITY_SIGNALS_EXPLAINED.md. "Verified" is
// deliberately NOT a tier label here — it means examiner verification, a
// separate from a validation score.
const TIER_CONFIG: Record<string, { bg: string; border: string; text: string; icon: typeof Shield; label: string }> = {
  excellent: { bg: 'rgba(34,197,94,0.10)', border: '#22c55e', text: '#15803d', icon: ShieldCheck, label: 'Excellent' },
  good:      { bg: 'rgba(59,130,246,0.10)', border: '#3b82f6', text: '#1d4ed8', icon: ShieldCheck, label: 'Good' },
  fair:      { bg: 'rgba(234,179,8,0.10)', border: '#eab308', text: '#a16207', icon: Shield, label: 'Fair' },
  poor:      { bg: 'rgba(239,68,68,0.08)', border: '#ef4444', text: '#dc2626', icon: ShieldAlert, label: 'Poor' },
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
  const [showTooltip, setShowTooltip] = useState(false)
  const badgeRef = useRef<HTMLButtonElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const detailsId = useId()
  const [position, setPosition] = useState({ left: 12, top: 12 })

  const tier = quality.tier?.toLowerCase() ?? ''
  const config = TIER_CONFIG[tier] || DEFAULT_CONFIG
  const IconComponent = config.icon
  const hasAlerts = (quality.active_alerts?.length ?? 0) > 0
  const hasCriticalAlert = (quality.active_alerts ?? []).some(a => a.severity === 'critical')

  // Close tooltip on outside click
  usePanelEffect(() => {
    if (!showTooltip) return
    const handler = (e: MouseEvent) => {
      if (
        badgeRef.current && !badgeRef.current.contains(e.target as Node) &&
        tooltipRef.current && !tooltipRef.current.contains(e.target as Node)
      ) {
        setShowTooltip(false)
      }
    }
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setShowTooltip(false); badgeRef.current?.focus() }
    }
    const place = () => {
      const anchor = badgeRef.current?.getBoundingClientRect()
      if (anchor) setPosition({ left: Math.max(12, Math.min(anchor.left, window.innerWidth - 292)), top: Math.max(12, Math.min(anchor.bottom + 8, window.innerHeight - 320)) })
    }
    place()
    tooltipRef.current?.focus()
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', dismiss, true)
    window.addEventListener('resize', place)
    return () => { document.removeEventListener('mousedown', handler); document.removeEventListener('keydown', dismiss, true); window.removeEventListener('resize', place) }

  }, [showTooltip])

  if (quality.score == null && !quality.tier) return null

  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <button
        ref={badgeRef}
        aria-expanded={showTooltip}
        aria-controls={showTooltip ? detailsId : undefined}
        aria-label={
          quality.score != null
            ? `Quality ${config.label}, score ${Math.round(quality.score)} of 100. Show details.`
            : `Quality ${config.label}. Show details.`
        }
        onClick={(e) => { e.stopPropagation(); setShowTooltip(!showTooltip) }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--workspace-space-4)',
          padding: "var(--workspace-space-2) var(--workspace-space-8)",
          borderRadius: 9999,
          fontSize: 'var(--workspace-font-meta)',
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
          // Red = critical (accuracy floor breached / run errored); amber =
          // warning (consistency drift, stale validation).
          <AlertTriangle size={10} style={{ color: hasCriticalAlert ? '#dc2626' : '#f59e0b', marginLeft: -2 }} />
        )}
      </button>

      {/* Rich tooltip */}
      {showTooltip && createPortal(
        <div
          ref={tooltipRef}
          id={detailsId} role="region" aria-label="Tool quality details" tabIndex={0}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'fixed',
            left: position.left, top: position.top,
            width: 280,
            maxHeight: `calc(100dvh - ${position.top + 12}px)`,
            overflowY: 'auto',
            overflowWrap: 'anywhere',
            maxWidth: 'calc(100vw - 24px)',
            background: '#fff',
            border: "1px solid var(--workspace-border)",
            borderRadius: 'var(--workspace-radius-medium)',
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 'var(--workspace-space-12)',
            zIndex: 1000,
            fontSize: 'var(--workspace-font-meta)',
            color: '#374151',
            lineHeight: 1.5,
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', marginBottom: 'var(--workspace-space-8)', paddingBottom: 'var(--workspace-space-8)', borderBottom: '1px solid #f3f4f6' }}>
            <IconComponent size={16} style={{ color: config.text }} />
            <span style={{ fontWeight: 600, fontSize: 'var(--workspace-font-control)' }}>
              {quality.score != null ? `Quality Score: ${Math.round(quality.score)}/100` : 'No Score'}
            </span>
          </div>

          <p style={{ margin: '0 0 8px', color: '#59616b' }}>Recorded validation describes the cases tested. Completion and permission to share do not establish correctness on new documents.</p>
          <button type="button" onClick={() => { setShowTooltip(false); badgeRef.current?.focus() }} aria-label="Close quality details" className="mb-2 underline">Close</button>
          {/* Metrics */}
          {(quality.accuracy != null || quality.consistency != null) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: "var(--workspace-space-4) var(--workspace-space-12)", marginBottom: 'var(--workspace-space-8)' }}>
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
              {quality.grade != null && (
                <>
                  <span style={{ color: '#6b7280' }}>Grade</span>
                  <span style={{ fontWeight: 500, textAlign: 'right' }}>{quality.grade}</span>
                </>
              )}
            </div>
          )}

          {/* Last validated */}
          <div style={{ color: '#59616b', fontSize: 'var(--workspace-font-meta)' }}>
            Last validated: {formatDate(quality.last_validated_at)}
          </div>

          {/* A high tier on a tiny test set is provisional, not proven — the
              docs' own FAQ says so; the badge should too. */}
          {quality.num_test_cases != null && quality.num_test_cases < 5 && (
            <div style={{ marginTop: 'var(--workspace-space-8)', paddingTop: 'var(--workspace-space-8)', borderTop: '1px solid #f3f4f6', fontSize: 'var(--workspace-font-meta)', color: '#92400e' }}>
              Scored on only {quality.num_test_cases} test case{quality.num_test_cases === 1 ? '' : 's'} —
              treat as provisional and add more before relying on it for high-stakes work.
            </div>
          )}

          {/* Stale validation plan (workflows) */}
          {quality.plan_stale && (
            <div style={{ marginTop: 'var(--workspace-space-8)', paddingTop: 'var(--workspace-space-8)', borderTop: '1px solid #f3f4f6', display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)', color: '#92400e' }}>
              <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>Validation plan is out of date with the workflow. Regenerate it before trusting this score.</span>
            </div>
          )}

          {/* Pending optimization recommendation */}
          {quality.optimization?.pending_recommendation && (
            <div style={{ marginTop: 'var(--workspace-space-8)', paddingTop: 'var(--workspace-space-8)', borderTop: '1px solid #f3f4f6', display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)', color: '#7c3aed' }}>
              <Sparkles size={12} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>
                Tuning found higher-scoring settings on the tested cases
                {quality.optimization.optimized_score != null && quality.optimization.baseline_score != null
                  ? ` (${Math.round(quality.optimization.optimized_score)} vs ${Math.round(quality.optimization.baseline_score)} baseline)`
                  : ''}
                {' '}(review and apply when ready).
              </span>
            </div>
          )}

          {/* Alerts */}
          {hasAlerts && (
            <div style={{ marginTop: 'var(--workspace-space-8)', paddingTop: 'var(--workspace-space-8)', borderTop: '1px solid #f3f4f6' }}>
              {quality.active_alerts!.map((alert, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 'var(--workspace-space-6)',
                    padding: "var(--workspace-space-4) 0",
                    fontSize: 'var(--workspace-font-meta)',
                    color: alert.severity === 'critical' ? '#dc2626' : '#92400e',
                  }}
                >
                  <AlertTriangle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span>{alert.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>, document.body
      )}
    </span>
  )
}
