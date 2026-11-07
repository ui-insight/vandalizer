import { useState } from 'react'
import { checkChatPractice } from '../../api/certification'
import type { ChatPracticeDefinition, ChatPracticeJudgment, ChatPracticeResult } from '../../types/certification'

const box = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-md border border-gray-400 px-3 py-2'
const button = 'min-h-11 rounded-lg border border-gray-300 px-3 py-2 font-semibold disabled:opacity-50'

// Optional Module 0 practice: the check reads the assigned document only; it saves nothing and awards nothing.
export function ChatPracticeCheck({ enrollmentId, practice }: { enrollmentId: string; practice: ChatPracticeDefinition }) {
  const [quote, setQuote] = useState(''), [page, setPage] = useState(1), [value, setValue] = useState('')
  const [judgment, setJudgment] = useState<'' | ChatPracticeJudgment>('')
  const [result, setResult] = useState<ChatPracticeResult | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function submit() {
    if (!judgment) return
    setBusy(true); setError('')
    try {
      setResult(await checkChatPractice(enrollmentId, { passage_quote: quote, page, value, unanswerable_judgment: judgment }))
    } catch { setError('The practice could not be checked. Try again.') }
    finally { setBusy(false) }
  }
  return <section aria-label="Scoped chat practice" className={box}>
    <h5 className="font-semibold">Scoped chat practice (optional)</h5>
    <ol className="list-decimal space-y-1 pl-5 text-sm">
      <li>Use Set Up Lab, then select the training document <span className="break-all">{practice.document}</span> as the chat source.</li>
      <li>Ask: “{practice.bounded_question}” Open the passage that supports the answer.</li>
      <li>Ask: “{practice.unanswerable_question}” Check whether the answer cites a passage.</li>
    </ol>
    <form aria-label="Check your scoped chat practice" className="space-y-3" onSubmit={e => { e.preventDefault(); void submit() }}>
      <label className="block text-sm">Supporting passage you opened (copy it exactly)<textarea className={control} rows={2} required minLength={5} maxLength={500} value={quote} onChange={e => setQuote(e.target.value)} /></label>
      <label className="block text-sm">Page of that passage<input type="number" min={1} max={20} required className={control} value={page} onChange={e => setPage(Number(e.target.value))} /></label>
      <label className="block text-sm">The value the passage states<input className={control} required maxLength={100} value={value} onChange={e => setValue(e.target.value)} /></label>
      <fieldset className="space-y-1 text-sm"><legend className="font-semibold">Did the source support the answer to the second question?</legend>
        <label className="flex items-center gap-2"><input type="radio" name="practice-judgment" checked={judgment === 'supported_by_source'} onChange={() => setJudgment('supported_by_source')} />Yes, a passage supports it</label>
        <label className="flex items-center gap-2"><input type="radio" name="practice-judgment" checked={judgment === 'not_stated_in_source'} onChange={() => setJudgment('not_stated_in_source')} />No, the source does not state it</label>
      </fieldset>
      <button className={button} disabled={busy || !judgment}>{busy ? 'Checking…' : 'Check my practice'}</button>
    </form>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {result && <div role="status" className="space-y-1 text-sm">
      <p className="font-semibold">{result.practice_complete ? 'Practice complete.' : 'Not yet.'}</p>
      <ul className="list-disc pl-5">{result.feedback.map(item => <li key={item}>{item}</li>)}</ul>
      <p className="text-gray-700">Practice only: nothing was saved and no credit changed.</p>
    </div>}
  </section>
}
