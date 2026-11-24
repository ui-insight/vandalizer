import { useState, useEffect, useRef } from 'react'
import { Link, Navigate, useParams } from '@tanstack/react-router'
import { Mail, CheckCircle, Loader2, ArrowLeft, ExternalLink, AlertCircle, Clock } from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { resendCredentials, type ResendResult } from '../api/demo'

// ---------------------------------------------------------------------------
// Credential recovery landing — the "Resend them" link in trial emails points
// here. Sends a fresh one-click sign-in link, or steers the user to the right
// next step (waitlist / renewal) instead of the dead "Not Found" this used to be.
// ---------------------------------------------------------------------------

export default function DemoResend() {
  const params = useParams({ strict: false }) as Record<string, string | undefined>
  const uuid = params?.uuid || ''

  const [result, setResult] = useState<ResendResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const request = useRef<{ uuid: string; attempt: number; promise: Promise<ResendResult> } | null>(null)

  useEffect(() => {
    if (!uuid) {
      setError('No trial reference provided.')
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true); setError(''); setResult(null)
    // A Strict Mode effect restart must not send a second email.
    if (!request.current || request.current.uuid !== uuid || request.current.attempt !== attempt) {
      request.current = { uuid, attempt, promise: resendCredentials(uuid) }
    }
    request.current.promise
      .then(value => { if (!cancelled) setResult(value) })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not request a sign-in link. Retry in a moment.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [uuid, attempt])

  // Out of tokens → send them to the warm top-up screen.
  if (result?.status === 'exhausted' && result.feedback_token) {
    return <Navigate to="/demo/trial-end" search={{ token: result.feedback_token }} />
  }

  return (
    <div className="bg-[#0a0a0a] text-gray-200 antialiased min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link
            to="/landing"
            search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined, register: undefined }}
            className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="text-xl font-bold text-white">Vandalizer</span>
          </Link>
          <a
            href="https://github.com/ui-insight/vandalizer"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-[#f1b300] transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            GitHub
          </a>
        </div>
      </nav>

      <div className="relative z-10 pt-28 pb-16">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
          {loading ? (
            <div role="status" aria-label="Requesting sign-in link" className="flex justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#f1b300]" />
            </div>
          ) : error ? (
            <div className="text-center py-20">
              <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-6" />
              <h2 className="text-2xl font-bold text-white mb-4">Something went wrong</h2>
              <p role="alert" className="text-gray-400">{error}</p>
              {uuid && <button onClick={() => setAttempt(value => value + 1)} className="mt-4 rounded-lg bg-white/10 px-6 py-3 font-bold text-white">Retry sign-in link</button>}
            </div>
          ) : result?.status === 'sent' ? (
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-green-500/20 bg-green-500/5">
                <Mail className="w-16 h-16 text-green-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">Check your inbox</h2>
                <p className="text-gray-400 mb-2">
                  We just emailed{result.email ? ` ${result.email}` : ' you'} a fresh one-click
                  sign-in link — no password needed.
                </p>
                <p className="text-sm text-gray-400">
                  The link works for the next 14 days. Don't see it? Check your spam folder.
                </p>
              </div>
            </div>
          ) : result?.status === 'pending' ? (
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
                <Clock className="w-16 h-16 text-[#f1b300] mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">You're on the waitlist</h2>
                <p className="text-gray-400">
                  Your trial hasn't been activated yet, so there's nothing to sign into. We'll
                  email you the moment a spot opens up.
                </p>
              </div>
            </div>
          ) : result?.status === 'send_failed' ? (
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-amber-500/20 bg-amber-500/5">
                <AlertCircle className="w-16 h-16 text-amber-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">That didn't go through</h2>
                <p className="text-gray-400">
                  We couldn't send the email just now. Retry when you are ready.
                </p>
                <button onClick={() => setAttempt(value => value + 1)} className="mt-4 rounded-lg bg-white/10 px-6 py-3 font-bold text-white">Retry sign-in link</button>
              </div>
            </div>
          ) : (
            // not_found
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
                <AlertCircle className="w-16 h-16 text-gray-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">We couldn't find that trial</h2>
                <p className="text-gray-400 mb-6">
                  This link may be out of date. You can request fresh access below.
                </p>
                <Link
                  to="/demo"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black hover:bg-[#d49e00] transition-colors"
                >
                  <CheckCircle className="w-5 h-5" /> Request access
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      <Footer />
    </div>
  )
}
