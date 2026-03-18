import { useState, useRef, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Loader2, type LucideIcon } from 'lucide-react'
import { cn } from '../../lib/cn'

export interface WizardStep {
  title: string
  content: ReactNode
}

interface SurveyWizardProps {
  steps: WizardStep[]
  onSubmit: () => void
  submitting: boolean
  submitLabel: string
  submitIcon: LucideIcon
  error?: string
}

export function SurveyWizard({
  steps,
  onSubmit,
  submitting,
  submitLabel,
  submitIcon: SubmitIcon,
  error,
}: SurveyWizardProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [direction, setDirection] = useState<'forward' | 'backward'>('forward')
  const [animating, setAnimating] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)

  const isFirst = currentStep === 0
  const isLast = currentStep === steps.length - 1

  function goTo(index: number) {
    if (index === currentStep || animating) return
    setDirection(index > currentStep ? 'forward' : 'backward')
    setAnimating(true)
    setTimeout(() => {
      setCurrentStep(index)
      setAnimating(false)
    }, 150)
  }

  function handleNext() {
    if (!formRef.current?.reportValidity()) return
    goTo(currentStep + 1)
  }

  function handlePrev() {
    goTo(currentStep - 1)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!formRef.current?.reportValidity()) return
    onSubmit()
  }

  function handleProgressClick(index: number) {
    // Only allow jumping back to completed steps
    if (index < currentStep) {
      goTo(index)
    }
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
      {/* Progress bar */}
      <div>
        <div className="flex gap-1">
          {steps.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handleProgressClick(i)}
              className={cn(
                'h-1.5 flex-1 rounded-full transition-colors',
                i <= currentStep ? 'bg-[#f1b300]' : 'bg-white/10',
                i < currentStep && 'cursor-pointer hover:bg-[#f1b300]/80',
                i >= currentStep && 'cursor-default',
              )}
            />
          ))}
        </div>
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-gray-400">
            Step {currentStep + 1} of {steps.length}
          </span>
          <span className="text-xs font-bold text-[#f1b300] uppercase tracking-wide">
            {steps[currentStep].title}
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-500/20 border border-red-500/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Step content */}
      <div
        className={cn(
          'transition-all duration-150',
          animating && direction === 'forward' && 'opacity-0 translate-x-4',
          animating && direction === 'backward' && 'opacity-0 -translate-x-4',
          !animating && 'opacity-100 translate-x-0',
        )}
      >
        <div className="space-y-5">{steps[currentStep].content}</div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2">
        {!isFirst ? (
          <button
            type="button"
            onClick={handlePrev}
            className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-5 py-3 font-bold text-white hover:bg-white/20 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>
        ) : (
          <div />
        )}

        {isLast ? (
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black transition-all hover:bg-[#d49e00] disabled:opacity-50"
          >
            {submitting ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" /> Submitting...
              </>
            ) : (
              <>
                <SubmitIcon className="w-5 h-5" /> {submitLabel}
              </>
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleNext}
            className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-6 py-3 font-bold text-black transition-all hover:bg-[#d49e00]"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </form>
  )
}
