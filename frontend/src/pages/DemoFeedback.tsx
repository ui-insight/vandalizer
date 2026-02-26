import { useState, useEffect, type FormEvent } from 'react'
import { Link, useSearch } from '@tanstack/react-router'
import {
  MessageSquare,
  CheckCircle,
  Loader2,
  ArrowLeft,
  Github,
  AlertCircle,
} from 'lucide-react'
import { Footer } from '../components/layout/Footer'
import { getPostQuestionnaire, submitPostQuestionnaire } from '../api/demo'
import type { FeedbackInfo } from '../types/demo'

// ---------------------------------------------------------------------------
// Configurable feedback fields
// ---------------------------------------------------------------------------

interface FeedbackField {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select' | 'rating'
  required: boolean
  placeholder?: string
  options?: string[]
}

const FEEDBACK_FIELDS: FeedbackField[] = [
  {
    key: 'overall_rating',
    label: 'How would you rate your overall experience?',
    type: 'select',
    required: true,
    options: ['Excellent', 'Good', 'Fair', 'Poor'],
  },
  {
    key: 'most_useful',
    label: 'What feature did you find most useful?',
    type: 'textarea',
    required: true,
    placeholder: 'e.g., Workflow builder, document extraction, chat...',
  },
  {
    key: 'missing_features',
    label: 'What features or capabilities were missing?',
    type: 'textarea',
    required: false,
    placeholder: 'Anything you wished Vandalizer could do...',
  },
  {
    key: 'would_recommend',
    label: 'Would you recommend Vandalizer to a colleague?',
    type: 'select',
    required: true,
    options: ['Definitely', 'Probably', 'Not sure', 'Probably not', 'Definitely not'],
  },
  {
    key: 'additional_comments',
    label: 'Any additional comments or suggestions?',
    type: 'textarea',
    required: false,
    placeholder: 'We appreciate your feedback!',
  },
]

// ---------------------------------------------------------------------------
// Main feedback page
// ---------------------------------------------------------------------------

export default function DemoFeedback() {
  const search = useSearch({ strict: false }) as Record<string, string | undefined>
  const token = search?.token || ''

  const [feedbackInfo, setFeedbackInfo] = useState<FeedbackInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!token) {
      setError('No feedback token provided.')
      setLoading(false)
      return
    }
    getPostQuestionnaire(token)
      .then((info) => {
        setFeedbackInfo(info)
        if (info.already_completed) {
          setSubmitted(true)
        }
      })
      .catch(() => setError('Invalid or expired feedback link.'))
      .finally(() => setLoading(false))
  }, [token])

  function updateAnswer(key: string, value: string) {
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await submitPostQuestionnaire(token, answers)
      setSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit feedback')
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
      </nav>

      <div className="relative z-10 pt-28 pb-16">
        <div className="max-w-lg mx-auto px-4 sm:px-6 lg:px-8">
          {loading ? (
            <div className="flex justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-[#f1b300]" />
            </div>
          ) : error && !feedbackInfo ? (
            <div className="text-center py-20">
              <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-6" />
              <h2 className="text-2xl font-bold text-white mb-4">Invalid Link</h2>
              <p className="text-gray-400">{error}</p>
              <Link
                to="/landing"
                className="inline-block mt-6 rounded-lg bg-white/10 px-6 py-3 font-bold text-white hover:bg-white/20 transition-colors"
              >
                Go to Homepage
              </Link>
            </div>
          ) : submitted ? (
            <div className="text-center py-12">
              <div className="p-8 rounded-2xl border border-green-500/20 bg-green-500/5">
                <CheckCircle className="w-16 h-16 text-green-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold text-white mb-4">Thank You!</h2>
                <p className="text-gray-400 mb-6">
                  Your feedback has been recorded. We appreciate you taking the time to share
                  your experience with Vandalizer.
                </p>
                <Link
                  to="/landing"
                  className="inline-block rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black hover:bg-[#d49e00] transition-colors"
                >
                  Back to Homepage
                </Link>
              </div>
            </div>
          ) : (
            <div className="p-8 rounded-2xl border border-white/10 bg-white/5">
              <div className="text-center mb-8">
                <MessageSquare className="w-12 h-12 text-[#f1b300] mx-auto mb-4" />
                <h2 className="text-2xl font-bold text-white mb-2">
                  Share Your Experience
                </h2>
                {feedbackInfo && (
                  <p className="text-gray-400">
                    Hi {feedbackInfo.name}, we'd love to hear about your time using Vandalizer.
                  </p>
                )}
              </div>

              {error && (
                <div className="mb-6 rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-5">
                {FEEDBACK_FIELDS.map((field) => (
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
                      <CheckCircle className="w-5 h-5" /> Submit Feedback
                    </>
                  )}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      <Footer />
    </div>
  )
}
