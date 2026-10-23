import { useEffect, useState } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { getInAppTopUp, requestInAppTopUp } from '../../api/demo'
import { formatTokens } from '../../lib/formatTokens'
import { groupBySection } from '../../lib/survey'
import { SurveyFieldRenderer } from '../survey/SurveyFieldRenderer'
import { SurveyWizard } from '../survey/SurveyWizard'
import { RENEWAL_NOTES_FIELDS } from '../survey/renewalNotesFields'
import type { InAppTopUpInfo } from '../../types/demo'

/** Fired on window after an in-app top-up, so the usage banner and chat can catch up. */
export const TRIAL_TOPPED_UP_EVENT = 'vandalizer:trial-topped-up'

const REFUSALS: Record<string, string> = {
  not_metered: "This account doesn't have a trial token allowance to top up.",
  email_unverified: 'Confirm your email address first, then you can top up here.',
  not_low: "You can top up once you've used most of your current tokens.",
  no_application: "This trial account can't be topped up here. Ask your administrator to add tokens.",
}

interface TrialTopUpDialogProps {
  open: boolean
  onClose: () => void
  /** Called after tokens were added. */
  onToppedUp?: () => void
}

/**
 * The trial-end screen's top-up, in the app. The emailed link was the only
 * way to top up, and a learner whose address couldn't receive it was stuck
 * mid-certification until an admin promoted the account (support ticket).
 * Same grant, same feedback: one click for someone just getting started, a
 * few notes from someone who has put it to work.
 */
export function TrialTopUpDialog({ open, onClose, onToppedUp }: TrialTopUpDialogProps) {
  const [info, setInfo] = useState<InAppTopUpInfo | null>(null)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [answers, setAnswers] = useState<Record<string, unknown>>({})

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setInfo(null); setLoadError(''); setError(''); setAnswers({})
    getInAppTopUp()
      .then((value) => { if (!cancelled) setInfo(value) })
      .catch(() => { if (!cancelled) setLoadError("Your token balance couldn't be loaded. Try again in a moment.") })
    return () => { cancelled = true }
  }, [open])

  if (!open) return null

  async function handleTopUp(notes?: Record<string, unknown>) {
    setSubmitting(true)
    setError('')
    try {
      await requestInAppTopUp(notes)
      window.dispatchEvent(new Event(TRIAL_TOPPED_UP_EVENT))
      onToppedUp?.()
      onClose()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The top-up did not go through. Try again in a moment.')
    } finally {
      setSubmitting(false)
    }
  }

  const steps = groupBySection(RENEWAL_NOTES_FIELDS).map((section) => ({
    title: section.name,
    content: (
      <>
        {section.fields.map((field) => (
          <div key={field.key}>
            {field.type !== 'info' && (
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {field.label}
                {field.required ? ' *' : ''}
              </label>
            )}
            <SurveyFieldRenderer field={field} value={answers[field.key]} onChange={(key, value) => setAnswers((prev) => ({ ...prev, [key]: value }))} />
          </div>
        ))}
      </>
    ),
  }))

  return (
    <>
      <div onClick={onClose} className="fixed inset-0 z-[1000] bg-black/40" />
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="trial-topup-title"
          onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
          className="fixed left-1/2 top-1/2 z-[1001] max-h-[90vh] w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-white/10 bg-[#111] p-6 text-gray-200 shadow-xl"
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <h2 id="trial-topup-title" className="text-lg font-bold text-white">Top up your trial tokens</h2>
            <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-gray-400 hover:text-white">
              <X size={18} />
            </button>
          </div>
          {loadError ? (
            <p role="alert" className="text-sm text-red-300">{loadError}</p>
          ) : !info ? (
            <div role="status" aria-label="Loading your token balance" className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          ) : !info.available ? (
            <p className="text-sm text-gray-300">{REFUSALS[info.reason ?? ''] ?? "This account can't be topped up right now."}</p>
          ) : info.engagement === 'low' ? (
            <div>
              <p className="mb-5 text-sm text-gray-300">
                You've used {formatTokens(info.tokens_used)} of {formatTokens(info.tokens_budget)} tokens.
                Add another {formatTokens(info.topup_tokens)}, on us, and keep going.
              </p>
              {error && <p role="alert" className="mb-4 rounded-md border border-red-500/30 bg-red-500/20 p-3 text-sm text-red-300">{error}</p>}
              <button
                type="button"
                onClick={() => handleTopUp()}
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-5 py-2.5 font-bold text-black hover:bg-[#d49e00] disabled:opacity-50"
              >
                {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Topping up…</> : <>Add {formatTokens(info.topup_tokens)} tokens</>}
              </button>
            </div>
          ) : (
            <div>
              <p className="mb-5 text-sm text-gray-300">
                You've put Vandalizer to real work: {formatTokens(info.tokens_used)} tokens' worth.
                Tell us a little about how it's going. Your notes go straight to the team, and
                another {formatTokens(info.topup_tokens)} tokens land on your account when you submit.
              </p>
              <SurveyWizard
                steps={steps}
                onSubmit={() => handleTopUp(answers)}
                submitting={submitting}
                submitLabel={`Get ${formatTokens(info.topup_tokens)} more tokens`}
                submitIcon={Sparkles}
                error={error}
              />
            </div>
          )}
        </div>
      </FocusTrap>
    </>
  )
}
