import { useState } from 'react'
import { Check, CheckCircle2, Lightbulb, Loader2, Star } from 'lucide-react'
import { cn } from '../../lib/cn'

type AssessmentQuestion = { key: string; question: string; options: readonly string[] }

function Stars({ count, max = 3, size = 16 }: { count: number; max?: number; size?: number }) {
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: max }).map((_, i) => (
        <Star
          key={i}
          size={size}
          className={cn(
            'transition-all duration-300',
            i < count ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300',
          )}
        />
      ))}
    </div>
  )
}

export const MODULE_ASSESSMENTS: Record<string, { title: string; subtitle: string; questions: readonly AssessmentQuestion[] }> = {
  ai_literacy: {
    title: 'Self-Assessment',
    subtitle: 'There are no wrong answers. This is about understanding your starting point.',
    questions: [
      {
        key: 'experience',
        question: 'Which best describes your experience with AI tools?',
        options: [
          'I have not used any AI tools',
          "I've tried a chatbot (ChatGPT, Copilot, etc.) a few times",
          'I use AI tools occasionally for work or personal tasks',
          'I use AI tools regularly and feel confident with them',
        ],
      },
      {
        key: 'comfort',
        question: 'When you think about using AI in research administration, how do you feel?',
        options: [
          "Skeptical \u2014 I worry about accuracy and whether it's appropriate for my work",
          "Cautious but curious \u2014 I want to understand it before forming an opinion",
          'Open to it if someone shows me how it helps with tasks I already do',
          "Enthusiastic \u2014 I'm looking for ways to integrate AI into my workflows",
        ],
      },
      {
        key: 'concern',
        question: 'What is your biggest concern about AI for research administration?',
        options: [
          "That it will make mistakes I won't catch, especially with compliance or financial data",
          "That it's a black box \u2014 I won't understand how it reaches its answers",
          "That it will change my role in ways I'm not comfortable with",
          "I don't have major concerns, but I want to learn the right way to use it",
        ],
      },
    ],
  },
  process_mapping: {
    title: 'Process Reflection',
    subtitle: 'Think about your actual daily work. There are no wrong answers.',
    questions: [
      {
        key: 'process',
        question: 'Which of these best describes a repetitive process in your work?',
        options: [
          'Processing incoming grant proposals (reading, extracting key details, filing)',
          'Reviewing progress reports (checking completeness, summarizing findings)',
          'Preparing compliance documentation (gathering data from multiple documents)',
          'Routing and tracking subaward agreements or award modifications',
        ],
      },
      {
        key: 'time_sink',
        question: 'When you do this process manually, what takes the most time?',
        options: [
          'Reading through documents to find specific information',
          'Re-typing data from documents into spreadsheets or forms',
          'Comparing information across multiple documents',
          'Writing summaries or reports based on document contents',
        ],
      },
      {
        key: 'judgment',
        question: 'Which part of this process most requires your expertise and judgment?',
        options: [
          'Deciding whether extracted information meets compliance requirements',
          'Interpreting ambiguous or unusual document content',
          'Making recommendations based on institutional knowledge and context',
          'All of the above \u2014 I need to review everything the AI produces',
        ],
      },
      {
        key: 'outcome',
        question: 'If you could build a workflow for this process, what would the ideal output be?',
        options: [
          'A structured spreadsheet with extracted data from all documents',
          'A summary report highlighting key findings and potential issues',
          'A compliance checklist showing what\'s present and what\'s missing',
          'A complete package ready for review (data + summary + checklist)',
        ],
      },
    ],
  },
  workflow_design: {
    title: 'Design Reflection',
    subtitle: 'Think about how you would structure workflows for your work.',
    questions: [
      {
        key: 'step_splitting',
        question: 'When you think about a process in your work, how would you decide where to split it into separate workflow steps?',
        options: [
          'Wherever I naturally take a break or hand off work to someone else',
          'When the type of work changes (reading \u2192 analyzing \u2192 writing)',
          'When I would want to verify output before proceeding to the next part',
          "I'm not sure yet \u2014 I need to see more examples before I can decide",
        ],
      },
      {
        key: 'pattern',
        question: 'For the documents your team processes, which workflow pattern seems most useful?',
        options: [
          'Extract then verify: pull structured data, then I review it',
          'Extract, analyze, report: pull data, reason over it, produce a deliverable',
          'Extract and compare: pull the same fields from multiple documents and compare them',
          'Compliance pipeline: extract, check against rules, flag issues automatically',
        ],
      },
      {
        key: 'concern',
        question: "What's your biggest concern about designing workflows for your team's processes?",
        options: [
          "I'm not sure how to break our processes into clear, discrete steps",
          "I worry about choosing the wrong task types for each step",
          "I'm concerned about maintaining and updating workflows as our processes change",
          'I need help getting buy-in from my team to adopt workflow-based approaches',
        ],
      },
      {
        key: 'human_role',
        question: 'When would you keep a step manual rather than adding it to the workflow?',
        options: [
          'When the step requires interpreting nuance or institutional context',
          'When the stakes are too high for any AI error (regulatory compliance decisions)',
          'When the input is too varied or unpredictable for consistent AI processing',
          'All of the above \u2014 human judgment is irreplaceable for certain decisions',
        ],
      },
    ],
  },
}

export function SelfAssessment({ moduleId, existingAnswers, onSubmit, submitting }: {
  moduleId: string
  existingAnswers?: Record<string, string>
  onSubmit: (answers: Record<string, string>) => void
  submitting: boolean
}) {
  const questions = MODULE_ASSESSMENTS[moduleId]
  if (!questions) return null

  const isCompleted = existingAnswers && questions.questions.every(q => existingAnswers[q.key])
  const [answers, setAnswers] = useState<Record<string, string>>(existingAnswers || {})

  const allAnswered = questions.questions.every(q => answers[q.key])

  if (isCompleted) {
    return (
      <div
        className="mb-5 p-5 border-2 border-green-200 bg-green-50/50"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          <CheckCircle2 size={20} className="text-green-600" />
          <h4 className="text-sm font-semibold text-green-800">Self-Assessment Complete</h4>
          <Stars count={3} size={14} />
        </div>
        <div className="space-y-3">
          {questions.questions.map(q => (
            <div key={q.key}>
              <p className="text-xs font-medium text-green-700 mb-0.5">{q.question}</p>
              <p className="text-sm text-green-900">{existingAnswers![q.key]}</p>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div
      className="mb-5 p-5 border-2 border-blue-200 bg-blue-50/30"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center gap-2 mb-1">
        <Lightbulb size={18} className="text-blue-600" />
        <h4 className="text-sm font-semibold text-blue-800">{questions.title}</h4>
      </div>
      <p className="text-xs text-gray-500 mb-4">
        {questions.subtitle}
      </p>

      <div className="space-y-5">
        {questions.questions.map(q => (
          <div key={q.key}>
            <p className="text-sm font-medium text-gray-900 mb-2">{q.question}</p>
            <div className="space-y-1.5">
              {q.options.map(option => (
                <label
                  key={option}
                  className={cn(
                    'flex items-start gap-2.5 p-2.5 border cursor-pointer transition-all text-sm',
                    answers[q.key] === option
                      ? 'border-blue-400 bg-blue-50'
                      : 'border-gray-200 bg-white hover:border-blue-200',
                  )}
                  style={{ borderRadius: 'var(--ui-radius, 12px)' }}
                >
                  <input
                    type="radio"
                    name={q.key}
                    value={option}
                    checked={answers[q.key] === option}
                    onChange={() => setAnswers(prev => ({ ...prev, [q.key]: option }))}
                    className="mt-0.5 accent-blue-600"
                  />
                  <span className="text-gray-700">{option}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={() => onSubmit(answers)}
        disabled={!allAnswered || submitting}
        className="mt-4 flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ borderRadius: 'var(--ui-radius, 12px)' }}
      >
        {submitting ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Saving...
          </>
        ) : (
          <>
            <Check size={14} />
            Submit Self-Assessment
          </>
        )}
      </button>
    </div>
  )
}
