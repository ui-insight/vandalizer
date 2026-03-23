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
import { SurveyFieldRenderer } from '../components/survey/SurveyFieldRenderer'
import { SurveyWizard, type WizardStep } from '../components/survey/SurveyWizard'
import { groupBySection } from '../lib/survey'
import type { SurveyField, WaitlistStatusResponse } from '../types/demo'

// ---------------------------------------------------------------------------
// Pre-survey field definitions
// ---------------------------------------------------------------------------

const PRE_SURVEY_FIELDS: SurveyField[] = [
  // --- Demographics ---
  {
    key: 'ra_department',
    label: 'Department you work in (select all that apply)',
    type: 'multiselect',
    required: true,
    section: 'Demographics',
    options: [
      'Pre-Award',
      'Post-Award',
      'Contracts',
      'Cost Accounting/Cost Compliance',
      'Financial/Invoicing',
      'Departmental Support',
      'Compliance (IACUC, IRB, etc.)',
      'IT Support',
      'Other',
      "I'm not in research administration",
    ],
  },
  {
    key: 'carnegie_classification',
    label: 'Institution Carnegie Classification (select all that apply)',
    type: 'multiselect',
    required: true,
    section: 'Demographics',
    options: [
      'Carnegie R1',
      'Carnegie R2',
      'Primarily Undergraduate Institution',
      'Community College',
      'Minority Serving Institution',
      'Academic Medical Center',
      'Independent Research Institute',
      'Emerging Research Institution',
      'Historically Black College / University',
      'Other',
    ],
  },

  // --- Where did you come from? ---
  {
    key: 'process_obstacles',
    label:
      'Please describe some of the process-based, technological obstacles or bottlenecks which you feel could be reduced or automated using AI.',
    type: 'textarea',
    required: true,
    section: 'Where did you come from?',
    placeholder: 'Describe current pain points in your workflow...',
  },
  {
    key: 'intended_use',
    label: 'How do you intend on using Vandalizer in your daily tasks?',
    type: 'textarea',
    required: true,
    section: 'Where did you come from?',
    placeholder: 'e.g., Grant proposal review, compliance checking, document extraction...',
  },

  // --- Task Time Estimates ---
  {
    key: 'time_rfa_checklist',
    label: 'Build an RFA checklist (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_foa_checklist',
    label: 'Build an FOA checklist (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_compliance_framework',
    label: 'Build a compliance framework from an award notice (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_effort_compliance',
    label: 'Create effort/time-and-effort compliance reports (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_management_plan',
    label: 'Build a management plan from an SF-425 (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_prior_approval',
    label: 'Create a prior approval requirements list (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },
  {
    key: 'time_subaward_extraction',
    label: 'Subaward extraction (minutes)',
    type: 'number',
    required: false,
    section: 'Task Time Estimates',
    placeholder: 'Minutes',
  },

  // --- AI Experience ---
  {
    key: 'ai_experience_level',
    label: 'What is your experience level with AI tools?',
    type: 'select',
    required: true,
    section: 'AI Experience',
    options: [
      'I have no experience with AI',
      'Less than a year',
      '1 - 2 years',
      '3 - 4 years',
      '5+ years',
    ],
  },
  {
    key: 'ai_tools_used',
    label: 'Which AI tools have you used? (select all that apply)',
    type: 'multiselect',
    required: false,
    section: 'AI Experience',
    options: [
      'ChatGPT',
      'Claude',
      'Microsoft Co-Pilot',
      'Google Gemini',
      'Perplexity',
      'Institution Specific Internal Tools',
      'Other',
    ],
  },
  {
    key: 'ai_work_frequency',
    label: 'How often do you use AI tools in your work?',
    type: 'select',
    required: true,
    section: 'AI Experience',
    options: [
      'Never',
      'Rarely (less than once weekly)',
      'Occasionally (a few times weekly)',
      'Moderately (once daily)',
      'Often (multiple times daily)',
    ],
  },

  // --- Pre-Experience Assessment ---
  {
    key: 'pre_assessment',
    label: 'Please rate your agreement with the following statements:',
    type: 'likert_group',
    required: false,
    section: 'Pre-Experience Assessment',
    statements: [
      { key: 'trust_ai', label: 'I trust AI outputs' },
      { key: 'want_ai', label: 'I want to use AI in my work life' },
      { key: 'not_worried_job', label: "I'm not worried AI will take my job" },
      { key: 'easy_to_use', label: 'I find AI easy to use' },
      { key: 'safe_use', label: 'I can use AI safely in my work' },
      { key: 'understand_models', label: 'I understand how AI models work' },
      {
        key: 'ethics_transparency',
        label:
          'It is unethical to utilize AI without being transparent about its use and explicitly disclosing it to the recipients',
      },
      {
        key: 'environmental_ethics',
        label:
          'I am worried that I am ethically complicit in environmental harms when using energy-intensive AI systems',
      },
      {
        key: 'comfortable_learning',
        label:
          'I am comfortable learning technical skills, even when there is a learning curve',
      },
    ],
  },

  // --- Excitement & Discovery ---
  {
    key: 'excitement_level',
    label: 'How excited are you to try Vandalizer?',
    type: 'select',
    required: true,
    section: 'Pre-Experience Assessment',
    options: ['1', '2', '3', '4', '5'],
  },
  {
    key: 'how_heard',
    label: 'How did you hear about Vandalizer?',
    type: 'textarea',
    required: false,
    section: 'Pre-Experience Assessment',
    placeholder: 'e.g., Conference, colleague, social media...',
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
            <label className="block text-sm font-medium text-gray-300 mb-2">Full Name *</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Grants Manager, Research Coordinator..."
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Email Address *</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT_CLASS}
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
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {field.label}
                {field.required ? ' *' : ''}
              </label>
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
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-[#0a0a0a]/80 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link to="/landing" search={{ error: undefined, invite_token: undefined }} className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
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
      </div>

      <Footer />
    </div>
  )
}
