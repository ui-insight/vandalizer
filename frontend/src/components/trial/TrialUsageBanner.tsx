import { useCallback, useEffect, useState } from 'react'
import { Gauge } from 'lucide-react'
import { getTrialUsage } from '../../api/demo'
import { useAuth } from '../../hooks/useAuth'
import { formatTokens } from '../../lib/formatTokens'
import type { TrialUsage } from '../../types/demo'
import { TRIAL_TOPPED_UP_EVENT, TrialTopUpDialog } from './TrialTopUpDialog'

/** Share of the allowance at which the banner appears; the in-app top-up opens here too. */
export const TRIAL_WARN_PERCENT = 80

/** Fired on window to open the top-up dialog from elsewhere (the chat's out-of-tokens notice). */
export const OPEN_TRIAL_TOPUP_EVENT = 'vandalizer:open-trial-topup'

/**
 * Warns a trial user before their AI tokens run out and offers the top-up in
 * the app. The only warning was an email at 80%, and the only way to top up
 * an emailed link; a learner ran out mid-certification with neither
 * (support ticket). Renders nothing below the warning line, for non-trial
 * users, and on deployments without a per-account allowance.
 */
export function TrialUsageBanner() {
  const { user } = useAuth()
  const isTrialUser = Boolean(user?.is_demo_user)
  const [usage, setUsage] = useState<TrialUsage | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  const refresh = useCallback(() => {
    if (!isTrialUser) {
      setUsage(null)
      return
    }
    getTrialUsage().then(setUsage).catch(() => setUsage(null))
  }, [isTrialUser])

  useEffect(() => {
    refresh()
    const open = () => setDialogOpen(true)
    window.addEventListener(TRIAL_TOPPED_UP_EVENT, refresh)
    window.addEventListener(OPEN_TRIAL_TOPUP_EVENT, open)
    return () => {
      window.removeEventListener(TRIAL_TOPPED_UP_EVENT, refresh)
      window.removeEventListener(OPEN_TRIAL_TOPUP_EVENT, open)
    }
  }, [refresh])

  const show = Boolean(usage?.enabled && usage.email_verified && usage.percent >= TRIAL_WARN_PERCENT)
  return (
    <>
      {show && usage && (
        <div role="status" className="flex flex-wrap items-center gap-3 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-200">
          <Gauge className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="flex-1 min-w-[16rem]">
            {usage.remaining > 0
              ? `You've used ${usage.percent}% of your trial AI tokens (${formatTokens(usage.remaining)} left). Certification work in chat doesn't count toward this.`
              : "You've used all of your trial AI tokens. Top up to keep using AI features. Everything you've built stays open."}
          </span>
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 px-3 py-1 font-semibold hover:bg-amber-500/20"
          >
            Top up
          </button>
        </div>
      )}
      <TrialTopUpDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </>
  )
}
