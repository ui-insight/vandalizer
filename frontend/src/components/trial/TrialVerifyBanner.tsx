import { useCallback, useEffect, useState } from 'react'
import { MailCheck, Loader2 } from 'lucide-react'
import { getTrialUsage } from '../../api/demo'
import { useAuth } from '../../hooks/useAuth'
import { useResendVerification } from '../../hooks/useResendVerification'

/**
 * Tells an unconfirmed trial user why AI features aren't responding, and gives
 * them the one action that fixes it.
 *
 * Without this the gate is silent until someone tries to run something and
 * gets an error mid-task. Renders nothing for everyone else: regular users,
 * confirmed trials, and deployments with the trial system switched off (where
 * the endpoint isn't even mounted, so a failed fetch is the normal case).
 */
export function TrialVerifyBanner() {
  const { user } = useAuth()
  const isTrialUser = Boolean(user?.is_demo_user)
  const [needsVerify, setNeedsVerify] = useState(false)
  const hide = useCallback(() => setNeedsVerify(false), [])
  const { resend, sending, sent, error } = useResendVerification(hide)

  useEffect(() => {
    // The session already says whether this is a trial account, so only trial
    // users pay for the lookup — on a deployment with the trial system off the
    // route isn't even mounted, and this way nobody requests it.
    if (!isTrialUser) {
      setNeedsVerify(false)
      return
    }
    let cancelled = false
    getTrialUsage()
      .then((usage) => {
        // Deliberately not gated on `usage.enabled`: a deployment that
        // uncapped per-account tokens has no meter to draw but still gates
        // AI on confirmation, and a hidden banner would leave that silent.
        if (!cancelled) setNeedsVerify(!usage.email_verified)
      })
      .catch(() => {
        // Metering unavailable — say nothing rather than guess at a gate.
      })
    return () => {
      cancelled = true
    }
  }, [isTrialUser])

  if (!needsVerify) return null

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-950"
    >
      <MailCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 min-w-[16rem]">
        Confirm your email to switch on AI features. Everything else — your
        documents and your workspace — works right now.
      </span>
      {sent ? (
        <span className="font-semibold">Sent — check your inbox.</span>
      ) : (
        <button
          type="button"
          onClick={resend}
          disabled={sending}
          className="inline-flex items-center gap-1.5 rounded-md border border-amber-700 bg-white px-3 py-1 font-semibold text-amber-950 hover:bg-amber-100 disabled:opacity-50"
        >
          {sending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Resend link
        </button>
      )}
      {error && <span role="alert" className="basis-full text-red-800">{error}</span>}
    </div>
  )
}
