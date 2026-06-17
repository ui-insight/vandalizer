import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

interface ColdStartHeroProps {
  headline: string
  /** Plain-language summary, e.g. "Typically $1–$5 and 10–20 minutes…" */
  body: ReactNode
  /** Optional numbered steps describing the next few minutes. */
  whatHappensNext?: string[]
  /** Bullets listing concrete benefits. */
  benefits?: string[]
  /** CTA button label. */
  ctaLabel: string
  /** CTA click handler. */
  onStart: () => void
  /** When true, render CTA in disabled state. */
  disabled?: boolean
  /** Title attribute for the disabled CTA (e.g. permission reason). */
  disabledReason?: string
  /** Theme — 'dark' matches KB/Extraction, 'light' matches Workflow editor. */
  theme?: 'dark' | 'light'
  /** Slot rendered above the CTA (e.g. error banner, "when to run" disclosure). */
  belowBody?: ReactNode
}

/**
 * Reusable empty-state hero for validation surfaces. Reassures with cost/time
 * bands, shows what happens next, and never starts anything destructive.
 * Extracted from the Extraction Autovalidate IdleHero so KB and Workflow can
 * use the same pattern.
 */
export function ColdStartHero({
  headline,
  body,
  whatHappensNext,
  benefits,
  ctaLabel,
  onStart,
  disabled = false,
  disabledReason,
  theme = 'dark',
  belowBody,
}: ColdStartHeroProps) {
  const isDark = theme === 'dark'

  const bg = isDark
    ? 'linear-gradient(135deg, #1f1f2e 0%, #1a1a1a 100%)'
    : 'linear-gradient(135deg, #faf5ff 0%, #f9fafb 100%)'
  const border = isDark ? 'rgba(124, 58, 237, 0.25)' : '#e9d5ff'
  const titleColor = isDark ? '#fff' : '#202124'
  const bodyColor = isDark ? '#bbb' : '#4b5563'
  const subtleColor = isDark ? '#999' : '#6b7280'
  const accent = isDark ? '#a78bfa' : '#7c3aed'
  const stepsBg = isDark ? 'rgba(124, 58, 237, 0.06)' : 'rgba(124, 58, 237, 0.06)'
  const stepsBorder = isDark ? 'rgba(124, 58, 237, 0.2)' : 'rgba(124, 58, 237, 0.25)'
  const stepsText = isDark ? '#ccc' : '#374151'

  return (
    <div style={{
      padding: 18,
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Sparkles size={18} style={{ color: accent }} />
        <h3 style={{ margin: 0, fontSize: 15, color: titleColor }}>{headline}</h3>
      </div>
      <p style={{ margin: '0 0 12px 0', fontSize: 13, color: bodyColor, lineHeight: 1.5 }}>
        {body}
      </p>
      {whatHappensNext && whatHappensNext.length > 0 && (
        <div style={{
          padding: '10px 12px',
          marginBottom: 12,
          backgroundColor: stepsBg,
          border: `1px solid ${stepsBorder}`,
          borderRadius: 6,
        }}>
          <div style={{
            fontSize: 10,
            color: accent,
            textTransform: 'uppercase',
            letterSpacing: 0.5,
            marginBottom: 6,
            fontWeight: 600,
          }}>
            What happens next
          </div>
          <ol style={{
            margin: 0,
            paddingLeft: 20,
            fontSize: 12,
            color: stepsText,
            lineHeight: 1.6,
          }}>
            {whatHappensNext.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
        </div>
      )}
      {benefits && benefits.length > 0 && (
        <ul style={{
          fontSize: 12,
          color: subtleColor,
          margin: '0 0 10px 0',
          paddingLeft: 18,
          lineHeight: 1.7,
        }}>
          {benefits.map((b, i) => <li key={i}>{b}</li>)}
        </ul>
      )}
      {belowBody}
      <button
        onClick={onStart}
        disabled={disabled}
        title={disabled ? disabledReason : ''}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 16px',
          fontSize: 13,
          fontWeight: 600,
          fontFamily: 'inherit',
          color: disabled ? (isDark ? '#555' : '#9ca3af') : '#fff',
          background: disabled
            ? (isDark ? '#222' : '#e5e7eb')
            : 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
          border: '1px solid ' + (disabled ? (isDark ? '#333' : '#d1d5db') : '#7c3aed'),
          borderRadius: 6,
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        <Sparkles size={14} />
        {ctaLabel}
      </button>
    </div>
  )
}
