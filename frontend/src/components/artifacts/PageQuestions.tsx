import { useEffect, useState } from 'react'
import { MessageCircleQuestion, MessageSquare, X } from 'lucide-react'
import * as api from '../../api/artifacts'
import { PageDialog } from './PagePrimitives'

/* Support ticket: team members and public-link viewers had no way to ask a
 * Page's owner a question or flag a figure, and the owner had nowhere to see
 * such feedback. The Page itself runs in a script-free sandbox, so a viewer
 * picks the part of the page from a list rather than clicking inside it. */

const errorText = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Try again.'

/** "Ask the owner" for a team member (uuid) or a public-link viewer (token). */
export function AskOwnerDialog({ uuid, token, revision, onClose, onSent }: {
  uuid?: string; token?: string; revision?: string; onClose: () => void; onSent: () => void
}) {
  const [anchors, setAnchors] = useState<api.PageAnchor[]>([])
  const [anchor, setAnchor] = useState('')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [website, setWebsite] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    const load = token ? api.publicQuestionAnchors(token) : uuid ? api.questionAnchors(uuid, revision) : null
    load?.then(r => { if (live) setAnchors(r.anchors) }).catch(() => { if (live) setAnchors([]) })
    return () => { live = false }
  }, [uuid, token, revision])
  const send = async () => {
    setBusy(true); setError('')
    try {
      if (token) await api.askPublicQuestion(token, { message: message.trim(), anchor_id: anchor || null, email: email.trim(), name: name.trim() || undefined, website })
      else if (uuid) await api.askQuestion(uuid, { message: message.trim(), anchor_id: anchor || null, revision })
      onSent()
    } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  const ready = !!message.trim() && (!token || /\S+@\S+\.\S+/.test(email.trim()))
  return <PageDialog title="Ask the owner" onClose={onClose} busy={busy}>
    <p>Ask about this page or flag a figure. The owner gets your question in Vandalizer{token ? ' and answers you by email' : ' and the answer comes back to your notifications'}.</p>
    {error && <p role="alert" className="page-alert">{error}</p>}
    <label className="block text-sm font-medium">About
      <select className="mt-2 w-full rounded-lg border border-slate-300 p-2 text-sm" aria-label="About" value={anchor} onChange={e => setAnchor(e.target.value)}>
        <option value="">The whole page</option>
        {anchors.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
      </select>
    </label>
    <label className="mt-3 block text-sm font-medium">Your question or note
      <textarea className="mt-2 min-h-28 w-full rounded-lg border border-slate-300 p-3 text-sm" value={message} maxLength={2000} onChange={e => setMessage(e.target.value)} placeholder="Is Equipment Y2 $20k or $15k? The budget justification says $15k." autoFocus />
    </label>
    {token && <>
      <label className="mt-3 block text-sm font-medium">Your email (for the answer)
        <input type="email" className="mt-2 w-full rounded-lg border border-slate-300 p-2 text-sm" value={email} maxLength={320} onChange={e => setEmail(e.target.value)} autoComplete="email" required />
      </label>
      <label className="mt-3 block text-sm font-medium">Your name (optional)
        <input className="mt-2 w-full rounded-lg border border-slate-300 p-2 text-sm" value={name} maxLength={120} onChange={e => setName(e.target.value)} autoComplete="name" />
      </label>
      {/* Left empty by people; bots fill it. */}
      <input type="text" tabIndex={-1} autoComplete="off" aria-hidden="true" className="page-question-trap" value={website} onChange={e => setWebsite(e.target.value)} name="website" />
      <p className="mt-2 text-xs text-slate-500">Your email is shared only with the page's owner.</p>
    </>}
    <div className="page-actions"><button className="page-button page-button-primary" disabled={busy || !ready} onClick={() => void send()}><MessageCircleQuestion size={16} />Send to owner</button><button className="page-button" disabled={busy} onClick={onClose}>Cancel</button></div>
  </PageDialog>
}

/** Answers the owner chose to show under this version of the page. */
export function PageNotes({ notes }: { notes?: api.PageNote[] }) {
  if (!notes?.length) return null
  return <section className="page-notes" aria-label="Notes from the page owner">
    <h2>Questions answered by the owner</h2>
    {notes.map((n, i) => <article key={i}>
      {n.about && <p className="page-note-about">About {n.about}</p>}
      <p className="page-note-question">{n.question}</p>
      <p className="page-note-answer">{n.answer}</p>
    </article>)}
  </section>
}

/** A team member's own questions about this page and the owner's answers. */
export function MyQuestions({ uuid, refresh }: { uuid: string; refresh: number }) {
  const [items, setItems] = useState<api.PageQuestion[]>([])
  useEffect(() => {
    let live = true
    api.myQuestions(uuid).then(r => { if (live) setItems(r) }).catch(() => { if (live) setItems([]) })
    return () => { live = false }
  }, [uuid, refresh])
  if (!items.length) return null
  return <section className="page-notes" aria-label="Your questions">
    <h2>Your questions</h2>
    {items.map(q => <article key={q.uuid}>
      {q.anchor_label && <p className="page-note-about">About {q.anchor_label}</p>}
      <p className="page-note-question">{q.message}</p>
      {q.answer ? <p className="page-note-answer">{q.answer.text}</p> : <p className="page-note-about">{q.status === 'closed' ? 'Closed by the owner without an answer.' : 'Waiting for the owner.'}</p>}
    </article>)}
  </section>
}

/** The owner's inbox for this page: answer, show on page, turn into a change request, close. */
export function OwnerQuestions({ uuid, focus, onShow, onRequestChanges, onClose, onChanged }: {
  uuid: string; focus?: string | null
  onShow: (question: api.PageQuestion) => void
  onRequestChanges: (text: string) => void
  onClose: () => void
  onChanged: () => void
}) {
  const [items, setItems] = useState<api.PageQuestion[] | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [showOnPage, setShowOnPage] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const load = () => api.listQuestions(uuid).then(setItems).catch(e => setError(errorText(e)))
  useEffect(() => { void load() }, [uuid]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const target = focus && items?.find(q => q.uuid === focus)
    if (target) { onShow(target); document.getElementById(`page-question-${target.uuid}`)?.scrollIntoView?.({ block: 'nearest' }) }
  }, [focus, items]) // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id); setError('')
    try { await fn(); await load(); onChanged() } catch (e) { setError(errorText(e)) } finally { setBusy('') }
  }
  const asker = (q: api.PageQuestion) => q.asker?.name && q.asker?.email ? `${q.asker.name} <${q.asker.email}>` : q.asker?.name || q.asker?.email || 'A viewer'
  return <PageDialog title="Questions about this page" onClose={onClose} wide>
    {error && <p role="alert" className="page-alert">{error}</p>}
    {items === null ? <p role="status">Loading questions…</p> : !items.length ? <p>No questions yet. Viewers with access can ask from the page; public-link viewers can ask when you allow it under Share.</p> :
      <ul className="page-questions">{items.map(q => <li key={q.uuid} id={`page-question-${q.uuid}`} className={q.uuid === focus ? 'page-question page-question--focus' : 'page-question'}>
        <header><strong>{asker(q)}</strong>{q.asker?.kind === 'public' && <span className="page-question-tag">Public link</span>}<span className="page-question-tag">{q.status === 'open' ? 'Open' : q.status === 'answered' ? 'Answered' : 'Closed'}</span>{q.version && <span>Version {q.version}</span>}</header>
        {q.anchor_label && <button type="button" className="page-text-button" onClick={() => onShow(q)}>About {q.anchor_label} · show on page</button>}
        <p className="page-note-question">{q.message}</p>
        {q.answer ? <p className="page-note-answer">{q.answer.text}{q.answer.show_on_page ? ' (shown on the page)' : ''}</p> : q.status === 'open' && <>
          <label className="block text-sm font-medium">Answer
            <textarea aria-label={`Answer ${asker(q)}`} className="mt-1 min-h-20 w-full rounded-lg border border-slate-300 p-2 text-sm" maxLength={4000} value={drafts[q.uuid] ?? ''} onChange={e => setDrafts(d => ({ ...d, [q.uuid]: e.target.value }))} />
          </label>
          <label className="mt-1 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!showOnPage[q.uuid]} onChange={e => setShowOnPage(s => ({ ...s, [q.uuid]: e.target.checked }))} />Show the question and answer on the page for everyone viewing version {q.version ?? 'this version'}</label>
        </>}
        <div className="page-actions">
          {q.status === 'open' && <button className="page-button page-button-primary" disabled={!!busy || !(drafts[q.uuid] ?? '').trim()} onClick={() => void run(q.uuid, () => api.answerQuestion(uuid, q.uuid, (drafts[q.uuid] ?? '').trim(), !!showOnPage[q.uuid]))}>Send answer</button>}
          <button className="page-button" disabled={!!busy} onClick={() => onRequestChanges(`A viewer asked${q.anchor_label ? ` about ${q.anchor_label}` : ''}: "${q.message}"\n\nUpdate the page to address this.`)}><MessageSquare size={16} />Turn into a change request</button>
          {q.status === 'open' && <button className="page-button" disabled={!!busy} onClick={() => void run(q.uuid, () => api.closeQuestion(uuid, q.uuid))}><X size={16} />Close without answering</button>}
        </div>
      </li>)}</ul>}
  </PageDialog>
}

/** Share-dialog settings: public questions and how the owner is named. */
export function QuestionSettings({ artifact, onSaved }: { artifact: api.Artifact; onSaved: () => void }) {
  const [busy, setBusy] = useState(false)
  const [label, setLabel] = useState(artifact.sharing_contact?.contact_label ?? '')
  const [error, setError] = useState('')
  const save = async (body: Parameters<typeof api.updateQuestionSettings>[1]) => {
    setBusy(true); setError('')
    try { await api.updateQuestionSettings(artifact.uuid, body); onSaved() } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }
  const hidden = !!artifact.sharing_contact?.hide_owner_name
  return <div className="page-question-settings">
    {error && <p role="alert" className="page-alert">{error}</p>}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy} checked={!!artifact.public_questions} onChange={e => void save({ public_questions: e.target.checked })} />Allow questions from link viewers. They leave an email address for your answer.</label>
    <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy} checked={!hidden} onChange={e => void save({ hide_owner_name: !e.target.checked })} />Show my name and organization on shared pages</label>
    {hidden && <label className="mt-2 block text-sm">Contact to show instead (optional)
      <span className="mt-1 flex gap-2"><input className="w-full rounded-lg border border-slate-300 p-2 text-sm" value={label} maxLength={120} onChange={e => setLabel(e.target.value)} placeholder="OSP pre-award team" /><button className="page-button" disabled={busy} onClick={() => void save({ contact_label: label })}>Save</button></span>
    </label>}
  </div>
}
