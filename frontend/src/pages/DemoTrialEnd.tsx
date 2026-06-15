import { useState, useEffect } from 'react'
import { Link, useSearch, useNavigate } from '@tanstack/react-router'
import {
  Sparkles,
  CheckCircle,
  Loader2,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  AlertCircle,
  Mail,
  Rocket,
} from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { useAuth } from '../hooks/useAuth'
import { getTrialEndInfo, requestTrialExtension } from '../api/demo'
import { SurveyFieldRenderer } from '../components/survey/SurveyFieldRenderer'
import { SurveyWizard } from '../components/survey/SurveyWizard'
import { RENEWAL_NOTES_FIELDS } from '../components/survey/renewalNotesFields'
import { groupBySection } from '../lib/survey'
import type { TrialEndInfo } from '../types/demo'

// ---------------------------------------------------------------------------
// End-of-trial screen — friendly renewal + beta positioning. Replaces the hard
// lockout dead-end. Token-authenticated (the lock token), no session required.
// ---------------------------------------------------------------------------

// Matches the Landing page's "Get in Touch" convention (no public support inbox).
const CONTACT_URL = 'https://github.com/ui-insight/vandalizer/issues'

export default function DemoTrialEnd() {
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token || ''
  const navigate = useNavigate()
  const { refreshUser } = useAuth()

  const [info, setInfo] = useState<TrialEndInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [extended, setExtended] = useState(false)
  const [answers, setAnswers] = useState<Record<string, unknown>>({})

  useEffect(() => {
    if (!token) {
      setError('No trial token provided.')
      setLoading(false)
      return
    }
    getTrialEndInfo(token)
      .then(setInfo)
      .catch(() => setError('This link is invalid or has expired.'))
      .finally(() => setLoading(false))
  }, [token])

  function updateAnswer(key: string, value: unknown) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  async function handleExtend(notes?: Record<string, unknown>) {
    setError('')
    setSubmitting(true)
    try {
      await requestTrialExtension(token, notes)
      setExtended(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not extend your trial.')
    } finally {
      setSubmitting(false)
    }
  }

  async function enterApp() {
    await refreshUser()
    navigate({
      to: '/',
      search: {
        mode: undefined,
        tab: undefined,
        workflow: undefined,
        extraction: undefined,
        automation: undefined,
        kb: undefined,
        workflow_share_token: undefined,
      },
    })
  }

  const sections = groupBySection(RENEWAL_NOTES_FIELDS)
  const steps = sections.map((sec) => ({
    title: sec.name,
    content: (
      <>
        {sec.fields.map((field) => (
          <div key={field.key}>
            {field.type !== 'info' && (
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {field.label}
                {field.required ? ' *' : ''}
              </label>
            )}
            <SurveyFieldRenderer field={field} value={answers[field.key]} onChange={updateAnswer} />
          </div>
        ))}
      </>
    ),
  }))

  return (
    <div className="bg-[#0a0a0a] text-gray-200 antialiased min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link
            to="/landing"
            search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined }}
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
            <div className="flex justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#f1b300]" />
            </div>
          ) : error && !info ? (
            <div className="text-center py-20">
              <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-6" />
              <h2 className="text-2xl font-bold text-white mb-4">Invalid Link</h2>
              <p className="text-gray-400">{error}</p>
              <Link
                to="/landing"
                search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined }}
                className="inline-block mt-6 rounded-lg bg-white/10 px-6 py-3 font-bold text-white hover:bg-white/20 transition-colors"
              >
                Go to Homepage
              </Link>
            </div>
          ) : extended ? (
            // --- Renewal succeeded ---
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-green-500/20 bg-green-500/5">
                <Rocket className="w-16 h-16 text-green-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">You're back in!</h2>
                <p className="text-gray-400 mb-6">
                  Your trial has been extended by another two weeks. Pick up right where you left
                  off — and thanks for helping shape Vandalizer.
                </p>
                <button
                  onClick={enterApp}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black hover:bg-[#d49e00] transition-colors"
                >
                  Enter Vandalizer <ArrowRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          ) : info && info.can_self_extend ? (
            // --- Can still self-extend ---
            <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
              <div className="text-center mb-8">
                <Sparkles className="w-12 h-12 text-[#f1b300] mx-auto mb-4" />
                <h2 className="text-2xl font-bold text-white mb-2">Your trial has wrapped up</h2>
                <p className="text-gray-400">
                  Hi {info.name} — Vandalizer is an evolving beta built for research offices, and
                  feedback from trial users like you is actively shaping where it goes next. Trial
                  access keeps going as new releases land.
                </p>
              </div>

              {info.engagement === 'low' ? (
                // Low engagement → frictionless one-click renewal
                <div className="text-center">
                  <p className="text-gray-300 mb-6">
                    Looks like you were just getting started. No problem — grab another two weeks
                    and take it for a proper spin.
                  </p>
                  {error && (
                    <div className="mb-4 rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
                      {error}
                    </div>
                  )}
                  <button
                    onClick={() => handleExtend()}
                    disabled={submitting}
                    className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-8 py-4 text-lg font-bold text-black hover:bg-[#d49e00] transition-colors disabled:opacity-50"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" /> Extending…
                      </>
                    ) : (
                      <>
                        Keep my trial going <ArrowRight className="w-5 h-5" />
                      </>
                    )}
                  </button>
                  <p className="mt-3 text-xs text-gray-500">Adds 14 more days, instantly.</p>
                </div>
              ) : (
                // Engaged → short notes in exchange for more time
                <div>
                  <p className="text-gray-300 mb-6">
                    Want another two weeks? Tell us a little about how it's going — your notes go
                    straight to the team, and you'll be back in the moment you submit.
                  </p>
                  <SurveyWizard
                    steps={steps}
                    onSubmit={() => handleExtend(answers)}
                    submitting={submitting}
                    submitLabel="Get 2 more weeks"
                    submitIcon={Sparkles}
                    error={error}
                  />
                </div>
              )}
            </div>
          ) : (
            // --- Cap reached → route to a human ---
            <div className="p-8 rounded-2xl border border-white/10 bg-white/5 text-center">
              <Mail className="w-12 h-12 text-[#f1b300] mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Let's keep this going</h2>
              <p className="text-gray-400 mb-6">
                {info ? `Hi ${info.name} — you` : 'You'}'ve made the most of your trial extensions.
                We'd love to talk about keeping Vandalizer in your office for good. Reach out and
                we'll sort out continued access.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <a
                  href={CONTACT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black hover:bg-[#d49e00] transition-colors"
                >
                  <Mail className="w-5 h-5" /> Get in touch
                </a>
                <Link
                  to="/demo/feedback"
                  search={{ token }}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-white/10 px-6 py-3 font-bold text-white hover:bg-white/20 transition-colors"
                >
                  <CheckCircle className="w-5 h-5" /> Share final feedback
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
