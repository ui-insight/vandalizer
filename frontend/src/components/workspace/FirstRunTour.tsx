import { useEffect, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

const STEPS = [
  {
    title: 'Welcome to Vandalizer 5.0',
    body: 'Use the Assistant to ask questions and carry out tasks. Open Files alongside the Library to run a saved prompt, extraction or workflow on your documents. On smaller screens, use the pane buttons to switch between them.',
  },
  {
    title: 'Start with your sources',
    body: 'Upload a document or attach a knowledge base when your question needs context. Open the source references in an answer to compare it with the original. Missing or incomplete sources can limit an answer.',
  },
  {
    title: 'Review what will run',
    body: 'Check the selected sources and proposed changes before approving an action. The Library holds reusable tools; Explore shows shared items, their inputs and outputs, and available validation evidence.',
  },
  {
    title: 'Learn at your own pace',
    body: 'Start the certification course from the Assistant home when you want a guided exercise. You can revisit this tour from home anytime. Email preferences are available on your Account page.',
  },
]

/** Optional, explicitly opened help. Never interrupts a first or returning session. */
export function FirstRunTour({ onDismiss }: { onDismiss: () => void }) {
  const [step, setStep] = useState(0)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true })
    contentRef.current?.scrollTo?.(0, 0)
  }, [step])
  const current = STEPS[step]
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
      <FocusTrap focusTrapOptions={{ initialFocus: '#first-run-tour-title', escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div role="dialog" aria-modal="true" aria-labelledby="first-run-tour-title" aria-describedby="first-run-tour-body"
          className="flex max-h-[calc(100dvh-32px)] w-full max-w-md flex-col overflow-hidden rounded-xl border border-gray-200 bg-white text-gray-900 shadow-xl"
          onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onDismiss() } }}>
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-200 px-4 py-3">
            <span className="text-sm font-semibold">Quick tour · {step + 1} of {STEPS.length}</span>
            <button type="button" onClick={onDismiss} aria-label="Dismiss tour" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100"><X className="h-5 w-5" /></button>
          </div>
          <div ref={contentRef} className="min-h-0 overflow-y-auto p-5">
            <h2 ref={headingRef} tabIndex={-1} id="first-run-tour-title" className="mb-3 text-xl font-semibold">{current.title}</h2>
            <p id="first-run-tour-body" className="text-sm leading-relaxed text-gray-700">{current.body}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 p-4">
            <button type="button" onClick={onDismiss} className="min-h-9 rounded-md px-2 text-sm text-gray-700 hover:bg-gray-100">Skip tour</button>
            <div className="flex gap-2">
              {step > 0 && <button type="button" onClick={() => setStep(value => value - 1)} className="inline-flex min-h-9 items-center gap-1 rounded-md border border-gray-300 px-3 text-sm hover:bg-gray-100"><ChevronLeft className="h-4 w-4" />Back</button>}
              <button type="button" onClick={() => step === STEPS.length - 1 ? onDismiss() : setStep(value => value + 1)} className="inline-flex min-h-9 items-center gap-1 rounded-md bg-highlight px-3 text-sm font-semibold text-highlight-text hover:bg-highlight-hover">
                {step === STEPS.length - 1 ? 'Get started' : <>Next<ChevronRight className="h-4 w-4" /></>}
              </button>
            </div>
          </div>
        </div>
      </FocusTrap>
    </div>
  )
}
