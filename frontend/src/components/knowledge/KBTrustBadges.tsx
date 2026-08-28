import { ShieldCheck, Sparkles, AlertTriangle } from 'lucide-react'
import type { KnowledgeBase, KBOptimizationStatus } from '../../types/knowledge'

// The two trust chips on a KB card, and what they actually mean.
//
// Verified and Optimized look alike and answer different questions:
//   Verified  — an administrator published this KB to the shared catalog.
//               It vouches for the CONTENT. Says nothing about settings.
//   Optimized — KB Autovalidate found retrieval settings that beat the
//               defaults on this KB's own test questions, and they were
//               APPLIED (they are what chat uses now). Says nothing about
//               who curated the content.
//
// Optimized also has to say whether it is still true: the settings were
// tuned against the sources and questions that existed at the time, and the
// backend marks the status stale once those have changed materially.

export const VERIFIED_KB_HOVER =
  'Verified — an administrator published this knowledge base to the shared catalog, vouching for its content. Not the same as Optimized, which is about retrieval settings.'

const fmtDate = (iso: string | null | undefined, withTime = false) => {
  if (!iso) return null
  const d = new Date(iso)
  return withTime ? d.toLocaleString() : d.toLocaleDateString()
}

/** Older API payloads carry only has_optimized_config / optimized_config_set_at. */
export function optimizationOf(kb: Pick<KnowledgeBase, 'optimization' | 'has_optimized_config' | 'optimized_config_set_at'>): KBOptimizationStatus | null {
  if (kb.optimization) return kb.optimization
  if (kb.has_optimized_config) {
    return { state: 'applied', applied_at: kb.optimized_config_set_at ?? null, stale: false, stale_reasons: [], tuned_keys: [] }
  }
  return null
}

export function optimizedBadgeTitle(opt: KBOptimizationStatus, withTime = false): string {
  const applied = fmtDate(opt.applied_at, withTime)
  const lastRun = fmtDate(opt.last_run_at, withTime)
  const tuned = opt.tuned_keys?.length ? ` Tuned: ${opt.tuned_keys.join(', ')}.` : ''
  if (opt.state === 'available') {
    return (
      `Optimization available — Validate & improve found better settings${lastRun ? ` on ${lastRun}` : ''}, ` +
      'but they were not applied (or were reverted), so chat still uses the defaults. ' +
      'Open the KB\'s Validation panel to review and apply them.'
    )
  }
  const head =
    `Optimized — settings tuned by Validate & improve on this KB's own test questions are APPLIED` +
    `${applied ? ` (applied ${applied})` : ''} and used by chat.${tuned}` +
    `${lastRun && lastRun !== applied ? ` Most recent optimization run: ${lastRun}.` : ''}`
  if (opt.state === 'stale') {
    return (
      `${head}\n\nSTALE: ${opt.stale_reasons.join(' ')} ` +
      'The tuned settings may no longer be the best fit — re-run Validate & improve.'
    )
  }
  return `${head} Not the same as Verified, which is about who curated the content.`
}

const chip = {
  display: 'inline-flex', alignItems: 'center', gap: 3,
  fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 8,
} as const

export function VerifiedBadge() {
  return (
    <span title={VERIFIED_KB_HOVER} style={{ ...chip, color: '#15803d', backgroundColor: '#dcfce7' }}>
      <ShieldCheck size={10} />
      Verified
    </span>
  )
}

/**
 * Optimized / Optimized · stale / Optimization available. The "available"
 * chip only renders for someone who can act on it (apply), otherwise it is
 * a nag nobody on the card can resolve.
 */
export function OptimizedBadge({ kb, withTime = false }: {
  kb: Pick<KnowledgeBase, 'optimization' | 'has_optimized_config' | 'optimized_config_set_at' | 'can_manage'>
  withTime?: boolean
}) {
  const opt = optimizationOf(kb)
  if (!opt) return null
  const title = optimizedBadgeTitle(opt, withTime)
  if (opt.state === 'available') {
    if (kb.can_manage === false) return null
    return (
      <span title={title} style={{
        ...chip, color: '#9ca3af', backgroundColor: 'rgba(156, 163, 175, 0.12)',
        border: '1px dashed rgba(156, 163, 175, 0.4)',
      }}>
        <Sparkles size={10} />
        Optimization available
      </span>
    )
  }
  if (opt.state === 'stale') {
    return (
      <span title={title} style={{
        ...chip, color: '#fbbf24', backgroundColor: 'rgba(245, 158, 11, 0.12)',
        border: '1px solid rgba(245, 158, 11, 0.35)',
      }}>
        <AlertTriangle size={10} />
        Optimized · stale
      </span>
    )
  }
  return (
    <span title={title} style={{
      ...chip, color: '#a78bfa', backgroundColor: 'rgba(124, 58, 237, 0.12)',
      border: '1px solid rgba(124, 58, 237, 0.3)',
    }}>
      <Sparkles size={10} />
      Optimized
    </span>
  )
}
