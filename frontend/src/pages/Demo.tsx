import { useState, type FormEvent } from 'react'
import { Link } from '@tanstack/react-router'
import {
  Clock,
  CheckCircle,
  Send,
  ArrowLeft,
  Loader2,
  Users,
  FileText,
  Cpu,
  ExternalLink,
  Mail,
} from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { submitDemoApplication, getWaitlistStatus, resendCredentials } from '../api/demo'
import { SurveyFieldRenderer } from '../components/survey/SurveyFieldRenderer'
import { SurveyWizard, type WizardStep } from '../components/survey/SurveyWizard'
import { PRE_SURVEY_FIELDS } from '../components/survey/preSurveyFields'
import { groupBySection } from '../lib/survey'
import type { WaitlistStatusResponse } from '../types/demo'

// ---------------------------------------------------------------------------
// Waitlist status check component
// ---------------------------------------------------------------------------

function StatusCheck() {
  const [uuid, setUuid] = useState('')
  const [status, setStatus] = useState<WaitlistStatusResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [resendMessage, setResendMessage] = useState('')

  async function handleCheck(e: FormEvent) {
    e.preventDefault()
    setError('')
    setResendMessage('')
    setLoading(true)
    try {
      const s = await getWaitlistStatus(uuid)
      setStatus(s)
    } catch {
      setError('Application not found. Please check your ID.')
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    setResending(true)
    setResendMessage('')
    setError('')
    try {
      const res = await resendCredentials(uuid)
      setResendMessage(res.message)
    } catch {
      setError('Unable to resend credentials. Please try again.')
    } finally {
      setResending(false)
    }
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    active: 'bg-green-500/20 text-green-400 border-green-500/30',
    expired: 'bg-red-500/20 text-red-400 border-red-500/30',
    completed: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }

  return (
    <div className="mt-8 p-6 rounded-xl border border-white/10 bg-white/5">
      <h3 className="text-lg font-bold text-white mb-4">Check Your Status</h3>
      <form onSubmit={handleCheck} className="flex gap-3">
        <input
          type="text"
          aria-label="Application ID"
          placeholder="Enter your application ID"
          value={uuid}
          onChange={(e) => setUuid(e.target.value)}
          className="flex-1 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
        />
        <button
          type="submit"
          disabled={loading || !uuid}
          className="rounded-lg bg-white/10 px-6 py-3 font-bold text-white hover:bg-white/20 disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Check'}
        </button>
      </form>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      {resendMessage && <p className="mt-3 text-sm text-green-400">{resendMessage}</p>}
      {status && (
        <div className="mt-4 p-4 rounded-lg bg-white/5 border border-white/10">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Status</span>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${statusColors[status.status] || 'bg-gray-500/20 text-gray-400'}`}>
              {status.status.toUpperCase()}
            </span>
          </div>
          {status.waitlist_position && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">Position</span>
              <span className="text-lg font-bold text-[#f1b300]">#{status.waitlist_position}</span>
            </div>
          )}
          {status.estimated_wait && (
            <p className="mt-2 text-sm text-gray-500">{status.estimated_wait}</p>
          )}
          {status.status === 'active' && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <p className="text-sm text-gray-400 mb-3">
                Lost your login credentials? We'll send a new password to the email on file.
              </p>
              <button
                onClick={handleResend}
                disabled={resending}
                className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300]/10 border border-[#f1b300]/20 px-4 py-2 text-sm font-bold text-[#f1b300] hover:bg-[#f1b300]/20 disabled:opacity-50 transition-colors"
              >
                {resending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
                Resend Login Credentials
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main demo page
// ---------------------------------------------------------------------------

export default function Demo() {
  const [submitted, setSubmitted] = useState(false)
  const [submittedUuid, setSubmittedUuid] = useState('')
  const [position, setPosition] = useState(0)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [title, setTitle] = useState('')
  const [email, setEmail] = useState('')
  const [organization, setOrganization] = useState('')
  const [answers, setAnswers] = useState<Record<string, unknown>>({})

  function updateAnswer(key: string, value: unknown) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit() {
    setError('')
    setSubmitting(true)
    try {
      const result = await submitDemoApplication({
        name,
        title,
        email,
        organization,
        questionnaire_responses: answers,
      })
      setSubmittedUuid(result.uuid)
      setPosition(result.waitlist_position)
      setSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit application')
    } finally {
      setSubmitting(false)
    }
  }

  const INPUT_CLASS =
    'w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50'

  const sections = groupBySection(PRE_SURVEY_FIELDS)

  const steps: WizardStep[] = [
    {
      title: 'Your Info',
      content: (
        <>
          <div>
            <label htmlFor="demo-name" className="block text-sm font-medium text-gray-300 mb-2">Full Name *</label>
            <input
              id="demo-name"
              type="text"
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="demo-title" className="block text-sm font-medium text-gray-300 mb-2">Title</label>
            <input
              id="demo-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Grants Manager, Research Coordinator..."
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="demo-email" className="block text-sm font-medium text-gray-300 mb-2">Email Address *</label>
            <input
              id="demo-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="demo-org" className="block text-sm font-medium text-gray-300 mb-2">University / Organization *</label>
            <input
              id="demo-org"
              type="text"
              required
              autoComplete="organization"
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              placeholder="e.g., University of Idaho"
              className={INPUT_CLASS}
            />
          </div>
        </>
      ),
    },
    ...sections.map((sec) => ({
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
              <SurveyFieldRenderer
                field={field}
                value={answers[field.key]}
                onChange={updateAnswer}
              />
            </div>
          ))}
        </>
      ),
    })),
  ]

  return (
    <div className="bg-[#0a0a0a] text-gray-200 antialiased min-h-screen">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-highlight">Skip to main content</a>
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link to="/landing" search={{ error: undefined, invite_token: undefined, admin: undefined, next: undefined }} className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-xl font-bold text-white">Vandalizer</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link to="/docs" className="text-sm text-gray-400 hover:text-[#f1b300] transition-colors">
              Docs
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
        </div>
      </nav>

      <main id="main-content" className="relative z-10 pt-28 pb-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Hero */}
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#f1b300]/10 border border-[#f1b300]/20 mb-8">
              <span className="flex h-2 w-2 rounded-full bg-[#f1b300] animate-pulse" />
              <span className="text-sm font-bold text-[#f1b300] tracking-wide uppercase">
                Free Two Week Trial
              </span>
            </div>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6">
              Try Vandalizer for Free
            </h1>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
              Get full platform access for a two week trial. Upload documents, build workflows,
              and experience AI-powered knowledge extraction firsthand.
            </p>
          </div>

          {/* Features row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
            {[
              { icon: FileText, title: 'Full Access', desc: 'Upload documents, run extractions, chat with AI' },
              { icon: Users, title: 'Team Workspace', desc: 'Collaborate with others from your organization' },
              { icon: Cpu, title: 'All AI Features', desc: 'Workflows, structured extraction, and more' },
            ].map((f) => (
              <div key={f.title} className="p-6 rounded-xl border border-white/10 bg-white/5">
                <f.icon className="w-8 h-8 text-[#f1b300] mb-4" />
                <h3 className="text-lg font-bold text-white mb-2">{f.title}</h3>
                <p className="text-gray-400">{f.desc}</p>
              </div>
            ))}
          </div>

          {submitted ? (
            /* Confirmation */
            <div className="max-w-lg mx-auto text-center">
              <div className="p-8 rounded-2xl border border-green-500/20 bg-green-500/5">
                <CheckCircle className="w-16 h-16 text-green-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">Application Received!</h2>
                <p className="text-gray-400 mb-6">
                  You're at position <span className="text-[#f1b300] font-bold">#{position}</span> on the waitlist.
                  Check your email for a confirmation message.
                </p>
                <div className="p-4 rounded-lg bg-white/5 border border-white/10 mb-6">
                  <p className="text-sm text-gray-500 mb-1">Your Application ID</p>
                  <p className="text-lg font-mono text-white">{submittedUuid}</p>
                </div>
                <div className="flex items-center gap-2 justify-center text-sm text-gray-500">
                  <Clock className="w-4 h-4" />
                  <span>We'll email you when your account is ready</span>
                </div>
              </div>
            </div>
          ) : (
            /* Signup form */
            <div className="max-w-2xl mx-auto">
              <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
                <h2 className="text-2xl font-bold text-white mb-6 text-center">
                  Request Trial Access
                </h2>

                <SurveyWizard
                  steps={steps}
                  onSubmit={handleSubmit}
                  submitting={submitting}
                  submitLabel="Request Trial Access"
                  submitIcon={Send}
                  error={error}
                />
              </div>

              <StatusCheck />
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}
