import { useEffect, useId, useRef, useState } from 'react'
import { HelpCircle } from 'lucide-react'
import type { KnowledgeCheckData } from '../../types/certification'
import { practiceChanged, readPractice, savePractice, type PracticeAttempt } from '../../lib/certificationPractice'

/** Formative practice only: answers never award certification credit. */
export function KnowledgeCheck({ data, storageKey }: { data: KnowledgeCheckData; storageKey?: string }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const id = useId()
  const fieldset = useRef<HTMLFieldSetElement>(null)
  const answer = selected === null ? null : data.options[selected]
  const [history, setHistory] = useState<PracticeAttempt[]>(() => {
    try { return storageKey ? readPractice(storageKey, data) : [] } catch { return [] }
  })
  const [storageUnavailable, setStorageUnavailable] = useState(false)
  useEffect(() => {
    if (!storageKey) return
    const refresh = (event: Event) => {
      if (event instanceof StorageEvent && event.key !== null && event.key !== storageKey) return
      if (event instanceof CustomEvent && event.detail !== storageKey) return
      try { setHistory(readPractice(storageKey, data)) } catch { setStorageUnavailable(true) }
    }
    window.addEventListener('storage', refresh)
    window.addEventListener(practiceChanged, refresh)
    return () => {
      window.removeEventListener('storage', refresh)
      window.removeEventListener(practiceChanged, refresh)
    }
  }, [storageKey, data])
  function checkAnswer() {
    if (selected === null || submitted) return
    setSubmitted(true)
    if (storageKey) {
      try { setHistory(savePractice(storageKey, data, selected)); setStorageUnavailable(false) }
      catch { setStorageUnavailable(true) }
    }
  }
  return (
    <fieldset ref={fieldset} className="my-4 min-w-0 rounded-lg border-2 border-indigo-200 bg-indigo-50/30 p-4">
      <legend className="flex items-center gap-2 px-1 text-xs font-bold text-indigo-800">
        <HelpCircle size={16} aria-hidden="true" /> Knowledge check · practice
      </legend>
      <p id={`${id}-question`} className="mb-3 text-sm font-medium text-gray-900">{data.question}</p>
      <div role="radiogroup" aria-labelledby={`${id}-question`} className="space-y-2">
        {data.options.map((option, index) => (
          <label key={index} className="flex cursor-pointer items-start gap-2 rounded-md border border-gray-300 bg-white p-3 text-sm text-gray-800 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-indigo-700">
            <input type="radio" name={id} checked={selected === index} onChange={() => { setSelected(index); setSubmitted(false) }} className="mt-0.5 shrink-0" />
            <span>{option.text}</span>
          </label>
        ))}
      </div>
      <button type="button" disabled={selected === null || submitted} onClick={checkAnswer} className="mt-3 min-h-11 rounded-md border border-indigo-800 bg-white px-3 py-2 text-sm font-medium text-indigo-900 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2">
        Check answer
      </button>
      <div role="status" aria-live="polite">
        {submitted && answer && <p className={`mt-3 text-sm ${answer.correct ? 'text-green-800' : 'text-amber-900'}`}>
          <strong>{answer.correct ? 'Correct. ' : 'Not quite. '}</strong>{answer.explanation}
          {!answer.correct && ' Choose another answer and check again.'}
        </p>}
      </div>
      <p className="mt-2 text-xs text-gray-600">Practice feedback only. This answer does not award module credit.</p>
      {storageUnavailable ? <p className="mt-2 text-xs text-amber-900" role="alert">Practice history could not be saved on this browser. Your feedback is still available for this visit.</p>
        : storageKey ? <p className="mt-2 text-xs text-gray-600">{history.length ? `${history.length} recent practice ${history.length === 1 ? 'attempt' : 'attempts'} saved on this browser. ` : 'Practice attempts are saved on this browser only. '}This history does not sync across devices.</p>
          : <p className="mt-2 text-xs text-gray-600">Practice for this visit only.</p>}
      {history.length > 0 && <details className="mt-2 text-sm text-gray-700">
        <summary className="min-h-11 cursor-pointer py-3 font-medium focus-visible:outline-2 focus-visible:outline-offset-2">Recent practice attempts</summary>
        <ol className="list-decimal space-y-2 pl-5">
          {history.map((attempt, index) => <li key={`${attempt.savedAt}:${index}`}>
            <span>{data.options[attempt.choice].correct ? 'Correct' : 'Not quite'}: {data.options[attempt.choice].text}</span>
          </li>)}
        </ol>
        <p className="mt-2 text-xs">Latest 20 attempts for this lesson revision. These are practice responses, not assessed results.</p>
        <button type="button" className="mt-2 min-h-11 rounded-md border border-gray-400 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2" onClick={() => {
          if (!storageKey) return
          try { localStorage.removeItem(storageKey); fieldset.current?.querySelector('input')?.focus(); setHistory([]); setStorageUnavailable(false); window.dispatchEvent(new CustomEvent(practiceChanged, { detail: storageKey })) }
          catch { setStorageUnavailable(true) }
        }}>Clear saved practice</button>
      </details>}
    </fieldset>
  )
}
