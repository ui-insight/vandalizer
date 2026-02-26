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
  Github,
} from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { submitDemoApplication, getWaitlistStatus } from '../api/demo'
import type { WaitlistStatusResponse } from '../types/demo'

// ---------------------------------------------------------------------------
// Configurable questionnaire fields — edit this array to change the form
// ---------------------------------------------------------------------------

interface QuestionField {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select'
  required: boolean
  placeholder?: string
  options?: string[]
}

const QUESTIONNAIRE_FIELDS: QuestionField[] = [
  {
    key: 'role',
    label: 'Your Role',
    type: 'select',
    required: true,
    options: [
      'Research Administrator',
      'Faculty / PI',
      'Graduate Student',
      'Staff',
      'IT / Developer',
      'Other',
    ],
  },
  {
    key: 'use_case',
    label: 'What would you like to use Vandalizer for?',
    type: 'textarea',
    required: true,
    placeholder: 'e.g., Grant proposal review, compliance checking, document extraction...',
  },
  {
    key: 'documents_per_week',
    label: 'How many documents do you process per week?',
    type: 'select',
    required: false,
    options: ['1-10', '11-50', '51-100', '100+'],
  },
  {
    key: 'how_heard',
    label: 'How did you hear about Vandalizer?',
    type: 'text',
    required: false,
    placeholder: 'e.g., Colleague, conference, website...',
  },
]

// ---------------------------------------------------------------------------
// Waitlist status check component
// ---------------------------------------------------------------------------

function StatusCheck() {
  const [uuid, setUuid] = useState('')
  const [status, setStatus] = useState<WaitlistStatusResponse | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleCheck(e: FormEvent) {
    e.preventDefault()
    setError('')
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
  const [email, setEmail] = useState('')
  const [organization, setOrganization] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})

  function updateAnswer(key: string, value: string) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const result = await submitDemoApplication({
        name,
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

  return (
    <div className="bg-[#0a0a0a] text-gray-200 antialiased min-h-screen">
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link to="/landing" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
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
              <Github className="w-4 h-4" />
              GitHub
            </a>
          </div>
        </div>
      </nav>

      <div className="relative z-10 pt-28 pb-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Hero */}
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#f1b300]/10 border border-[#f1b300]/20 mb-8">
              <span className="flex h-2 w-2 rounded-full bg-[#f1b300] animate-pulse" />
              <span className="text-sm font-bold text-[#f1b300] tracking-wide uppercase">
                Free 2-Week Demo
              </span>
            </div>
            <h1 className="text-4xl md:text-5xl font-bold text-white mb-6">
              Try Vandalizer for Free
            </h1>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
              Get full platform access for 2 weeks. Upload documents, build workflows,
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
            <div className="max-w-lg mx-auto">
              <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
                <h2 className="text-2xl font-bold text-white mb-6 text-center">
                  Request Demo Access
                </h2>

                {error && (
                  <div className="mb-6 rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
                    {error}
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Full Name *</label>
                    <input
                      type="text"
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">Email Address *</label>
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">University / Organization *</label>
                    <input
                      type="text"
                      required
                      value={organization}
                      onChange={(e) => setOrganization(e.target.value)}
                      placeholder="e.g., University of Idaho"
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
                    />
                  </div>

                  {/* Dynamic questionnaire fields */}
                  {QUESTIONNAIRE_FIELDS.map((field) => (
                    <div key={field.key}>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        {field.label}{field.required ? ' *' : ''}
                      </label>
                      {field.type === 'text' && (
                        <input
                          type="text"
                          required={field.required}
                          value={answers[field.key] || ''}
                          onChange={(e) => updateAnswer(field.key, e.target.value)}
                          placeholder={field.placeholder}
                          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
                        />
                      )}
                      {field.type === 'textarea' && (
                        <textarea
                          required={field.required}
                          value={answers[field.key] || ''}
                          onChange={(e) => updateAnswer(field.key, e.target.value)}
                          placeholder={field.placeholder}
                          rows={3}
                          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white placeholder-gray-500 focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50 resize-none"
                        />
                      )}
                      {field.type === 'select' && (
                        <select
                          required={field.required}
                          value={answers[field.key] || ''}
                          onChange={(e) => updateAnswer(field.key, e.target.value)}
                          className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white focus:border-[#f1b300]/50 focus:outline-none focus:ring-1 focus:ring-[#f1b300]/50"
                        >
                          <option value="">Select...</option>
                          {field.options?.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ))}

                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full rounded-lg bg-[#f1b300] px-4 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" /> Submitting...
                      </>
                    ) : (
                      <>
                        <Send className="w-5 h-5" /> Request Demo Access
                      </>
                    )}
                  </button>
                </form>
              </div>

              <StatusCheck />
            </div>
          )}
        </div>
      </div>

      <Footer />
    </div>
  )
}
