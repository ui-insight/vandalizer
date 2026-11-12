import { useCallback, useState } from 'react'
import { resendVerificationEmail } from '../api/demo'

/** Shown when the confirmation email can't be sent: the user can't fix the
 *  mail service, so name the person who can let them in. */
export const RESEND_FAILED_MESSAGE =
  "We couldn't send the email. Try again in a few minutes. If it still doesn't arrive, contact your administrator, who can confirm your account for you."

/**
 * Re-sends the confirm-your-email link for the signed-in trial user.
 *
 * Shared by the banner and the chat error, so both offer the same working
 * action and the same next step when sending fails.
 */
export function useResendVerification(onAlreadyVerified?: () => void) {
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [alreadyVerified, setAlreadyVerified] = useState(false)
  const [error, setError] = useState('')

  const resend = useCallback(async () => {
    setSending(true)
    setError('')
    try {
      const result = await resendVerificationEmail()
      if (result.already_verified) {
        setAlreadyVerified(true)
        onAlreadyVerified?.()
      } else if (result.ok) setSent(true)
      else setError(RESEND_FAILED_MESSAGE)
    } catch {
      setError(RESEND_FAILED_MESSAGE)
    } finally {
      setSending(false)
    }
  }, [onAlreadyVerified])

  return { resend, sending, sent, alreadyVerified, error }
}
