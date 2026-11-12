import { Loader2 } from 'lucide-react'
import { useResendVerification } from '../../hooks/useResendVerification'

/**
 * The action under a chat error raised because the trial account's email
 * isn't confirmed yet.
 *
 * Sending the same message again can't succeed until the address is
 * confirmed, so there is no Retry while it isn't: the one useful step is a
 * new link, and when that can't be sent, who to ask.
 */
export function UnverifiedEmailAction({ onRetry }: { onRetry?: () => void }) {
  const { resend, sending, sent, alreadyVerified, error } = useResendVerification()

  // Confirmed in the meantime (the emailed link, or an administrator): now
  // sending the message again can work, so offer it.
  if (alreadyVerified) {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
          >
            Send my message again
          </button>
        )}
        <span role="status" className="text-xs text-red-600/80">
          Your email is confirmed.{onRetry ? '' : ' Send your message again.'}
        </span>
      </div>
    )
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {sent ? (
        <span role="status" className="text-xs font-medium text-red-700">
          Sent. Check your inbox, open the link, then send your message again.
        </span>
      ) : (
        <>
          <button
            type="button"
            onClick={resend}
            disabled={sending}
            className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
          >
            {sending && <Loader2 size={12} className="animate-spin" />}
            Resend link
          </button>
          <span className="text-xs text-red-600/80">
            Your message wasn't sent to the assistant. Send it again once your email is confirmed.
          </span>
        </>
      )}
      {error && <span role="alert" className="basis-full text-xs text-red-700">{error}</span>}
    </div>
  )
}
