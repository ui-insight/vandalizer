import { useEffect, useState } from 'react'
import {
  MessageSquare,
  BadgeCheck,
  Award,
  Settings,
  ChevronRight,
  X,
  Sparkles,
} from 'lucide-react'

const STORAGE_KEY = 'vandalizer:first-run-tour-dismissed'

interface TourStep {
  icon: React.ElementType
  accent: string
  title: string
  body: string
}

const STEPS: TourStep[] = [
  {
    icon: MessageSquare,
    accent: 'text-highlight',
    title: 'Welcome to Vandalizer 5.0',
    body:
      'The chat on your left is the whole product. Ask it to search your files, run extractions, query knowledge bases, or dispatch workflows — all in plain English.',
  },
  {
    icon: BadgeCheck,
    accent: 'text-green-400',
    title: 'Every answer is validated',
    body:
      'Results from validated templates carry a quality badge with accuracy, consistency, and test-case count. Hover the badge for the full breakdown.',
  },
  {
    icon: Award,
    accent: 'text-blue-400',
    title: 'Learn by doing',
    body:
      'Open the Certification panel from the top nav. Module 1 walks through the agentic chat in about 10 minutes and earns you 50 XP.',
  },
  {
    icon: Settings,
    accent: 'text-gray-300',
    title: 'You control your inbox',
    body:
      'Email preferences live on your Account page — opt in or out of tutorials, activity nudges, and announcements anytime.',
  },
]

export function FirstRunTour() {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setOpen(true)
      }
    } catch {
      // localStorage disabled — skip the tour
    }
  }, [])

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // ignore
    }
    setOpen(false)
  }

  if (!open) return null

  const s = STEPS[step]
  const Icon = s.icon
  const isLast = step === STEPS.length - 1

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-white/10 bg-[#171717] shadow-2xl">
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss tour"
          className="absolute top-3 right-3 p-1.5 rounded-md text-gray-500 hover:text-white hover:bg-white/5 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4 text-xs font-bold uppercase tracking-wide text-highlight">
            <Sparkles className="w-3.5 h-3.5" />
            Vandalizer 5.0
            <span className="ml-auto text-gray-500 font-normal">
              {step + 1} / {STEPS.length}
            </span>
          </div>
          <div className="flex items-start gap-4">
            <div className={`shrink-0 p-2.5 rounded-lg bg-white/5 border border-white/10 ${s.accent}`}>
              <Icon className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-bold text-white mb-2">{s.title}</h2>
              <p className="text-sm text-gray-400 leading-relaxed">{s.body}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 mt-6">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 flex-1 rounded-full transition-colors ${
                  i === step ? 'bg-highlight' : i < step ? 'bg-highlight/30' : 'bg-white/10'
                }`}
              />
            ))}
          </div>

          <div className="flex items-center justify-between mt-6">
            <button
              type="button"
              onClick={dismiss}
              className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
            >
              Skip tour
            </button>
            {isLast ? (
              <button
                type="button"
                onClick={dismiss}
                className="inline-flex items-center gap-1.5 rounded-lg bg-highlight px-4 py-2 text-sm font-bold text-highlight-text transition-colors hover:bg-highlight-hover"
              >
                Get started
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
                className="inline-flex items-center gap-1.5 rounded-lg bg-highlight px-4 py-2 text-sm font-bold text-highlight-text transition-colors hover:bg-highlight-hover"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
