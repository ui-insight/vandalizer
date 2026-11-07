import { useEffect, useRef, useState } from 'react'
import { Check, Crosshair, Flag, MessageCircleQuestion, MessageSquare, X } from 'lucide-react'
import * as api from '../../api/pageFeedback'
import type { PageFeedbackItem } from '../../api/pageFeedback'
import type { PageSpot } from './PublishedPageContent'

// Page feedback (support ticket): viewers of a shared or public page ask its
// owner about a spot on it, and the owner answers, resolves, or turns the
// question into a Request changes. The page frame does the picking and the
// highlighting; this panel holds everything else.

const errorText = (e: unknown) => e instanceof Error ? e.message : 'That could not be sent. Try again.'

function when(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** What the page frame should do while this panel is open. */
export interface FrameControl {
  picking: boolean
  spot: PageSpot | null
}

type Audience =
  | { kind: 'member'; uuid: string; revision: string }
  | { kind: 'public'; token: string }

/** "Ask the owner" for team members and public-link viewers. */
export function AskOwnerPanel({ audience, picked, onFrame, focus, sharedBy, publicQuestions, answers, onAsked }: {
  audience: Audience
  /** The spot the viewer clicked in the frame while picking. */
  picked: PageSpot | null
  onFrame: (control: FrameControl) => void
  focus?: string | null
  sharedBy: string
  publicQuestions: boolean
  answers: PageFeedbackItem[]
  onAsked: () => void
}) {
  const [step, setStep] = useState<'idle' | 'picking' | 'writing'>('idle')
  const [spot, setSpot] = useState<PageSpot | null>(null)
  const [kind, setKind] = useState<'question' | 'flag'>('question')
  const [message, setMessage] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [website, setWebsite] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState('')
  const canAsk = audience.kind === 'member' || publicQuestions

  useEffect(() => {
    if (step === 'picking' && picked) { setSpot(picked); setStep('writing'); onFrame({ picking: false, spot: picked }) }
  }, [picked, step, onFrame])

  const start = () => { setSent(''); setError(''); setSpot(null); setStep('picking'); onFrame({ picking: true, spot: null }) }
  const cancel = () => { setStep('idle'); setSpot(null); setMessage(''); onFrame({ picking: false, spot: null }) }
  const submit = async () => {
    setBusy(true); setError('')
    try {
      if (audience.kind === 'member') await api.askPageOwner(audience.uuid, { revision: audience.revision, anchor: spot, message, kind })
      else await api.askPublicPageOwner(audience.token, { anchor: spot, message, kind, name, email, website })
      setSent(audience.kind === 'public' && !email.trim()
        ? 'Sent to the owner. Without an email address, any answer appears here only if the owner shows it on the page.'
        : 'Sent to the owner. You’ll get their answer ' + (audience.kind === 'member' ? 'in your notifications.' : 'by email.'))
      setStep('idle'); setSpot(null); setMessage(''); onFrame({ picking: false, spot: null }); onAsked()
    } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }

  return <section className="page-feedback" aria-label="Questions for the owner">
    <p className="page-feedback-owner">{sharedBy}</p>
    {answers.length > 0 && <ul className="page-feedback-list" aria-label="Answers from the owner">
      {answers.map(item => <li key={item.uuid} className={item.uuid === focus ? 'is-focused' : undefined}>
        <FeedbackSummary item={item} />
        {item.answer && <p className="page-feedback-answer"><strong>{item.answer.by_name || 'The owner'}:</strong> {item.answer.text}</p>}
        {!item.answer && <p className="page-feedback-meta">Waiting for an answer.</p>}
        {item.anchor.text && <button type="button" className="page-text-button" onClick={() => onFrame({ picking: false, spot: item.anchor })}><Crosshair size={13} /> Show on page</button>}
      </li>)}
    </ul>}
    {!canAsk ? null : step === 'idle' ? <div className="page-actions">
      <button type="button" className="page-button" onClick={start}><MessageCircleQuestion size={16} />Ask the owner</button>
    </div> : step === 'picking' ? <div className="page-feedback-picking" role="status">
      <Crosshair size={16} aria-hidden /> Click the figure, row or section you’re asking about.
      <button type="button" className="page-text-button" onClick={() => { setStep('writing'); onFrame({ picking: false, spot: null }) }}>Ask about the whole page</button>
      <button type="button" className="page-text-button" onClick={cancel}>Cancel</button>
    </div> : <form className="page-feedback-form" onSubmit={e => { e.preventDefault(); void submit() }}>
      <p>{spot?.text ? <>About: <q>{spot.text}</q> <button type="button" className="page-text-button" onClick={start}>Pick again</button></> : 'About the whole page.'}</p>
      <fieldset className="page-feedback-kind"><legend className="sr-only">Kind</legend>
        <label><input type="radio" name="kind" checked={kind === 'question'} onChange={() => setKind('question')} /> Question</label>
        <label><input type="radio" name="kind" checked={kind === 'flag'} onChange={() => setKind('flag')} /> Flag a problem</label>
      </fieldset>
      <label>{kind === 'flag' ? 'What looks wrong?' : 'Your question'}<textarea required maxLength={2000} value={message} onChange={e => setMessage(e.target.value)} autoFocus /></label>
      {audience.kind === 'public' && <>
        <label>Your name (optional)<input maxLength={120} value={name} onChange={e => setName(e.target.value)} autoComplete="name" /></label>
        <label>Email for the answer (optional)<input type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></label>
        <p className="page-feedback-meta">Only the owner sees your name and email. Your email is used only to send the answer.</p>
        <label className="page-feedback-trap" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={website} onChange={e => setWebsite(e.target.value)} /></label>
      </>}
      {error && <p role="alert" className="page-alert">{error}</p>}
      <div className="page-actions">
        <button type="submit" className="page-button page-button-primary" disabled={busy || !message.trim()}>{busy ? 'Sending…' : 'Send to the owner'}</button>
        <button type="button" className="page-button" onClick={cancel} disabled={busy}>Cancel</button>
      </div>
    </form>}
    {sent && <p role="status" className="page-notice">{sent}</p>}
  </section>
}

function FeedbackSummary({ item }: { item: PageFeedbackItem }) {
  return <>
    <p className="page-feedback-meta">
      {item.kind === 'flag' ? <Flag size={12} aria-hidden /> : <MessageCircleQuestion size={12} aria-hidden />}{' '}
      {item.author_name} · version {item.version} · {when(item.created_at)}
      {item.status !== 'open' && <> · {item.status === 'resolved' ? 'Resolved' : 'Answered'}</>}
    </p>
    {item.anchor.text && <p className="page-feedback-spot">“{item.anchor.text}”</p>}
    <p className="page-feedback-message">{item.message}</p>
  </>
}

/** The owner's inbox of questions on one page. */
export function OwnerFeedbackPanel({ uuid, onFrame, focus, onRequestChanges }: {
  uuid: string
  onFrame: (control: FrameControl) => void
  focus?: string | null
  onRequestChanges: (text: string) => void
}) {
  const [data, setData] = useState<Extract<api.PageFeedbackList, { role: 'owner' }> | null>(null)
  const [error, setError] = useState('')
  const [answering, setAnswering] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [onPage, setOnPage] = useState(false)
  const [busy, setBusy] = useState(false)
  const [contact, setContact] = useState('')
  const focused = useRef<HTMLLIElement>(null)

  const load = async () => {
    try {
      const list = await api.listPageFeedback(uuid, '')
      if (list.role === 'owner') { setData(list); setContact(list.settings.contact ?? '') }
    } catch (e) { setError(errorText(e)) }
  }
  useEffect(() => { void load() }, [uuid]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const item = data?.items.find(i => i.uuid === focus)
    if (item) { focused.current?.scrollIntoView?.({ block: 'nearest' }); if (item.anchor.text) onFrame({ picking: false, spot: item.anchor }) }
  }, [data, focus, onFrame])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await fn(); await load() } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  if (!data) return error ? <p role="alert" className="page-alert">{error}</p> : null
  const open = data.items.filter(i => i.status === 'open').length

  return <section className="page-feedback" aria-label="Questions from viewers">
    <h2>Questions from viewers{data.items.length > 0 && <span className="page-feedback-count"> · {open} open</span>}</h2>
    {error && <p role="alert" className="page-alert">{error}</p>}
    {data.items.length === 0 && <p className="page-feedback-meta">No questions yet. People you share this page with can click a figure or section and ask you about it.</p>}
    <ul className="page-feedback-list">
      {data.items.map(item => <li key={item.uuid} ref={item.uuid === focus ? focused : undefined} className={item.uuid === focus ? 'is-focused' : undefined}>
        <FeedbackSummary item={item} />
        {item.author_email && <p className="page-feedback-meta">Reply goes to {item.author_email}</p>}
        {item.answer && <p className="page-feedback-answer"><strong>Your answer{item.answer.on_page ? ' (shown on the page)' : ''}:</strong> {item.answer.text}</p>}
        {answering === item.uuid ? <form className="page-feedback-form" onSubmit={e => { e.preventDefault(); void act(async () => { await api.answerPageFeedback(uuid, item.uuid, answer, onPage); setAnswering(null); setAnswer('') }) }}>
          <label>Your answer<textarea required maxLength={4000} value={answer} onChange={e => setAnswer(e.target.value)} autoFocus /></label>
          <label className="page-feedback-check"><input type="checkbox" checked={onPage} onChange={e => setOnPage(e.target.checked)} /> Also show it on the page as a short note, for everyone who opens it</label>
          <p className="page-feedback-meta">{item.author_kind === 'member' ? `${item.author_name} gets it in their notifications.` : item.author_email ? 'It’s emailed to the person who asked.' : 'They left no email; they’ll only see it if you show it on the page.'}</p>
          <div className="page-actions"><button type="submit" className="page-button page-button-primary" disabled={busy || !answer.trim()}>Send answer</button><button type="button" className="page-button" onClick={() => setAnswering(null)}>Cancel</button></div>
        </form> : <div className="page-actions">
          {item.anchor.text && <button type="button" className="page-text-button" onClick={() => onFrame({ picking: false, spot: item.anchor })}><Crosshair size={13} /> Show on page</button>}
          <button type="button" className="page-button" disabled={busy} onClick={() => { setAnswering(item.uuid); setAnswer(item.answer?.text ?? ''); setOnPage(item.answer?.on_page ?? false) }}><MessageSquare size={14} />{item.answer ? 'Edit answer' : 'Answer'}</button>
          <button type="button" className="page-button" disabled={busy} onClick={() => onRequestChanges(api.asChangeRequest(item))}>Turn into Request changes</button>
          {item.status === 'resolved'
            ? <button type="button" className="page-text-button" disabled={busy} onClick={() => void act(() => api.setPageFeedbackStatus(uuid, item.uuid, item.answer ? 'answered' : 'open'))}><X size={13} /> Reopen</button>
            : <button type="button" className="page-text-button" disabled={busy} onClick={() => void act(() => api.setPageFeedbackStatus(uuid, item.uuid, 'resolved'))}><Check size={13} /> Resolve</button>}
        </div>}
      </li>)}
    </ul>
    <details className="page-feedback-settings"><summary>Who can ask, and your contact line</summary>
      <label className="page-feedback-check"><input type="checkbox" checked={data.settings.public_questions} disabled={busy}
        onChange={e => void act(() => api.updatePageFeedbackSettings(uuid, { public_questions: e.target.checked }))} /> Let people with the public link ask questions (they may leave an email address for your answer)</label>
      <p className="page-feedback-meta">Team members you share the page with can always ask.</p>
      <form onSubmit={e => { e.preventDefault(); void act(() => api.updatePageFeedbackSettings(uuid, { contact })) }}>
        <label>Contact shown on the page<input maxLength={200} value={contact} placeholder="Office of Sponsored Programs, osp@example.edu" onChange={e => setContact(e.target.value)} /></label>
        <p className="page-feedback-meta">Shown as: {data.shared_by}</p>
        <button type="submit" className="page-button" disabled={busy}>Save contact</button>
      </form>
    </details>
  </section>
}
